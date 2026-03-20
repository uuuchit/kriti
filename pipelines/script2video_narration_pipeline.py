"""Narration-synced script-to-video pipeline.

Extends Script2VideoPipeline to generate TTS narration per shot, use
narration duration for shot video length, and mux narration audio
into the final output.
"""

import os
import json
import math
import logging
import asyncio
from typing import Dict, List, Optional

import numpy as np
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips

from pipelines.script2video_pipeline import Script2VideoPipeline
from interfaces import CharacterInScene, ShotDescription
from tools.render_backend import RenderBackend
from utils.narration import extract_narration_text

# Veo duration constraints (seconds)
VALID_DURATIONS = [4, 6, 8]
DEFAULT_SHOT_DURATION = 8
MIN_SHOT_DURATION = 4
MAX_SHOT_DURATION = 8


class Script2VideoNarrationPipeline(Script2VideoPipeline):
    """Pipeline that syncs video shot durations to narration audio."""

    def __init__(
        self,
        chat_model,
        image_generator,
        video_generator,
        audio_generator,
        working_dir: str,
    ):
        super().__init__(
            chat_model=chat_model,
            image_generator=image_generator,
            video_generator=video_generator,
            working_dir=working_dir,
        )
        self.audio_generator = audio_generator
        self._shot_durations: Dict[int, int] = {}

    @classmethod
    def init_from_config(cls, config_path: str):
        """Initialize from YAML config; requires audio_generator section."""
        import yaml
        from dotenv import load_dotenv
        from langchain.chat_models import init_chat_model
        from utils.config import resolve_env_vars

        load_dotenv()
        with open(config_path, "r") as f:
            config = resolve_env_vars(yaml.safe_load(f))

        if "audio_generator" not in config:
            raise ValueError(
                "Narration pipeline requires 'audio_generator' in config. "
                "Use configs/script2video_narration.yaml."
            )

        chat_model = init_chat_model(**config["chat_model"]["init_args"])
        backend = RenderBackend.from_config(config)

        return cls(
            chat_model=chat_model,
            image_generator=backend.image_generator,
            video_generator=backend.video_generator,
            audio_generator=backend.audio_generator,
            working_dir=config["working_dir"],
        )

    async def generate_narration_for_shots(
        self,
        shot_descriptions: List[ShotDescription],
    ) -> Dict[int, float]:
        """Generate TTS for each shot and return shot_idx -> raw duration (seconds).

        Uses narration_text (sacred, plain text) if available,
        falls back to extract_narration_text(audio_desc) for backward compat.
        """
        durations: Dict[int, float] = {}

        async def process_shot(shot: ShotDescription) -> None:
            # Prefer narration_text (plain, no parsing) over audio_desc extraction
            text = getattr(shot, 'narration_text', None) or ''
            if not text.strip():
                text = extract_narration_text(shot.audio_desc)

            narration_path = os.path.join(
                self.working_dir, "shots", f"{shot.idx}", "narration.wav"
            )
            os.makedirs(os.path.dirname(narration_path), exist_ok=True)

            if not text.strip():
                durations[shot.idx] = DEFAULT_SHOT_DURATION
                return

            if os.path.exists(narration_path):
                try:
                    clip = AudioFileClip(narration_path)
                    durations[shot.idx] = clip.duration
                    clip.close()
                    return
                except Exception as e:
                    logging.warning(f"Shot {shot.idx}: could not load narration: {e}")

            try:
                audio_output = await self.audio_generator.generate_single_audio(text=text)
                audio_output.save(narration_path)
                durations[shot.idx] = audio_output.duration_sec
            except Exception as e:
                logging.warning(f"Shot {shot.idx}: TTS failed ({e}), using default duration")
                durations[shot.idx] = DEFAULT_SHOT_DURATION

        await asyncio.gather(
            *[process_shot(shot) for shot in shot_descriptions],
            return_exceptions=True,
        )
        return durations

    @staticmethod
    def _plan_segments(narration_dur: float) -> List[int]:
        """Split narration duration into a list of valid Veo segment durations (4/6/8s).

        Greedy: fill with 8s segments, then pick the best valid duration for remainder.
        Total of segments >= narration_dur (short surplus is fine — we trim at assembly).
        """
        if narration_dur <= 8:
            return [min(VALID_DURATIONS, key=lambda d: abs(d - narration_dur))]
        segments = []
        remaining = narration_dur
        while remaining > 0:
            if remaining <= 8:
                segments.append(min(VALID_DURATIONS, key=lambda d: abs(d - remaining)))
                break
            segments.append(8)
            remaining -= 8
        return segments

    async def generate_video_for_single_shot(
        self,
        shot_description: ShotDescription,
    ) -> None:
        """Generate video segment(s) for a shot to cover full narration duration.

        If narration > 8s, generates multiple Veo segments using the last frame
        of each segment as the first frame of the next for visual continuity.
        For the final segment, uses last_frame.png (if available) as Veo's
        last_frame target so the shot lands on the intended end state.
        """
        shot_dir = os.path.join(self.working_dir, "shots", f"{shot_description.idx}")
        video_path = os.path.join(shot_dir, "video.mp4")
        if os.path.exists(video_path):
            print(f"🚀 Skipped generating video for shot {shot_description.idx}, already exists.")
            return

        await self.frame_events[shot_description.idx]["first_frame"].wait()
        if shot_description.variation_type in ("medium", "large"):
            if shot_description.idx in self.frame_events and "last_frame" in self.frame_events[shot_description.idx]:
                await self.frame_events[shot_description.idx]["last_frame"].wait()

        first_frame = os.path.join(shot_dir, "first_frame.png")
        last_frame = os.path.join(shot_dir, "last_frame.png")
        has_last_frame = os.path.exists(last_frame)

        narration_dur = self._shot_durations.get(shot_description.idx, DEFAULT_SHOT_DURATION)
        segments = self._plan_segments(narration_dur)
        prompt = shot_description.motion_desc + "\n" + shot_description.audio_desc

        print(f"🎬 Shot {shot_description.idx}: narration={narration_dur:.1f}s → segments={segments} (total={sum(segments)}s) last_frame={'✅' if has_last_frame else '❌'}")

        seg_paths = []
        ref_frame = first_frame
        for seg_i, seg_dur in enumerate(segments):
            seg_path = os.path.join(shot_dir, f"video_{seg_i}.mp4")
            is_last_seg = (seg_i == len(segments) - 1)

            if os.path.exists(seg_path):
                print(f"  🚀 Segment {seg_i} already exists.")
            else:
                # For final segment: use last_frame as Veo target if available
                # Note: Veo interpolation (first+last frame) requires 8s duration
                if is_last_seg and has_last_frame and seg_dur == 8:
                    ref_images = [ref_frame, last_frame]
                    print(f"  🎬 Generating segment {seg_i} ({seg_dur}s) with last_frame target...")
                else:
                    ref_images = [ref_frame]
                    print(f"  🎬 Generating segment {seg_i} ({seg_dur}s)...")

                video_output = await self.video_generator.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=ref_images,
                    duration=seg_dur,
                )
                video_output.save(seg_path)
                print(f"  ☑️ Segment {seg_i} saved.")

            seg_paths.append(seg_path)

            # Extract last frame for next segment's continuity
            if not is_last_seg:
                next_frame = os.path.join(shot_dir, f"seg_{seg_i}_last_frame.png")
                if not os.path.exists(next_frame):
                    clip = VideoFileClip(seg_path)
                    last_arr = clip.get_frame(clip.duration - 0.05)
                    clip.close()
                    from PIL import Image
                    Image.fromarray(last_arr.astype(np.uint8)).save(next_frame)
                ref_frame = next_frame

        # Concatenate segments into final shot video
        if len(seg_paths) == 1:
            import shutil
            shutil.copy2(seg_paths[0], video_path)
        else:
            clips = [VideoFileClip(p) for p in seg_paths]
            concat = concatenate_videoclips(clips)
            concat.write_videofile(video_path, codec="libx264", preset="fast", logger=None)
            concat.close()
            for c in clips:
                c.close()

        print(f"☑️ Shot {shot_description.idx} video ready ({sum(segments)}s).")

    async def __call__(
        self,
        script: str,
        user_requirement: str,
        style: str,
        characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    ) -> str:
        """Run narration-synced pipeline. Returns path to final narrated video."""
        if characters is None:
            characters = await self.extract_characters(script=script)

        if character_portraits_registry is None:
            character_portraits_registry_path = os.path.join(
                self.working_dir, "character_portraits_registry.json"
            )
            if os.path.exists(character_portraits_registry_path):
                with open(character_portraits_registry_path, "r", encoding="utf-8") as f:
                    character_portraits_registry = json.load(f)
                print(f"🚀 Loaded {len(character_portraits_registry)} character portraits.")
            else:
                print("🔍 Generating character portraits...")
                character_portraits_registry = await self.generate_character_portraits(
                    characters=characters,
                    character_portraits_registry=None,
                    style=style,
                )
                with open(character_portraits_registry_path, "w", encoding="utf-8") as f:
                    json.dump(character_portraits_registry, f, ensure_ascii=False, indent=4)
                print(f"☑️ Generated character portraits.")

        storyboard = await self.design_storyboard(
            script=script,
            characters=characters,
            user_requirement=user_requirement,
        )

        shot_descriptions = await self.decompose_visual_descriptions(
            shot_brief_descriptions=storyboard,
            characters=characters,
        )

        # Generate narration and compute per-shot durations
        print("🔊 Generating narration for each shot...")
        self._shot_durations = await self.generate_narration_for_shots(shot_descriptions)
        print(f"☑️ Narration durations: {self._shot_durations}")

        camera_tree = await self.construct_camera_tree(shot_descriptions=shot_descriptions)

        priority_shot_idxs = [
            c.parent_cam_idx
            for c in camera_tree
            if c.parent_cam_idx is not None
        ]
        tasks = [
            self.generate_frames_for_single_camera(
                camera=camera,
                shot_descriptions=shot_descriptions,
                characters=characters,
                character_portraits_registry=character_portraits_registry,
                priority_shot_idxs=priority_shot_idxs,
            )
            for camera in camera_tree
        ]
        video_tasks = [
            self.generate_video_for_single_shot(shot_description=sd)
            for sd in shot_descriptions
        ]
        tasks.extend(video_tasks)
        await asyncio.gather(*tasks, return_exceptions=True)

        # Concatenate videos and mux narration
        final_video_path = os.path.join(self.working_dir, "final_video_narrated.mp4")
        if os.path.exists(final_video_path):
            print(f"🚀 Skipped final assembly, already exists.")
            return final_video_path

        print("🎬 Assembling final narrated video...")
        video_clips = []
        for sd in shot_descriptions:
            vpath = os.path.join(self.working_dir, "shots", f"{sd.idx}", "video.mp4")
            if os.path.exists(vpath):
                video_clips.append(VideoFileClip(vpath))
            else:
                logging.warning(f"Shot {sd.idx} video missing, skipping.")

        if not video_clips:
            print("❌ No videos generated.")
            return ""

        final_video = concatenate_videoclips(video_clips)

        # Build narration track and set as audio
        narration_paths = [
            os.path.join(self.working_dir, "shots", f"{sd.idx}", "narration.wav")
            for sd in shot_descriptions
        ]
        narration_clips = []
        for p in narration_paths:
            if os.path.exists(p):
                try:
                    narration_clips.append(AudioFileClip(p))
                except Exception as e:
                    logging.warning(f"Could not load narration {p}: {e}")

        if narration_clips:
            narration_audio = concatenate_audioclips(narration_clips)
            final_video = final_video.set_audio(narration_audio)
            for nc in narration_clips:
                nc.close()
        else:
            logging.warning("No narration clips found; output will use video audio or be silent.")

        final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
        final_video.close()
        print(f"☑️ Final narrated video saved to {final_video_path}.")
        return final_video_path
