"""Narration-first pipeline: narration text -> synced video.

Uses the same steps as script2video (Characters, Portraits, Storyboard,
Decompose, Camera tree, Frames, Video) with narration as primary input.
Narration and visuals stay in sync via TTS-driven shot durations.
"""

import os
import json
import logging
import asyncio
from typing import Dict, List, Optional

import numpy as np
from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, concatenate_audioclips
from moviepy.video.fx import CrossFadeIn, CrossFadeOut, FadeOut

from pipelines.script2video_narration_pipeline import Script2VideoNarrationPipeline, DEFAULT_SHOT_DURATION
from interfaces import CharacterInScene, ShotDescription, ShotBriefDescription


class Narration2VideoPipeline(Script2VideoNarrationPipeline):
    """Pipeline: narration text -> video with synced visuals and audio.

    Subclasses Script2VideoNarrationPipeline and uses design_storyboard_from_narration
    instead of design_storyboard. All other steps (Characters, Portraits, Decompose,
    Camera tree, Frames, Video) are identical. Narration-visual sync is preserved
    via TTS duration per shot and sequential mux.
    """

    @staticmethod
    def _fix_narration_text(storyboard, narration: str):
        """Ensure every shot has narration_text from the original narration.

        If the LLM left narration_text null, split the original narration
        into sentences and distribute them across shots in order.
        """
        filled = [s for s in storyboard if s.narration_text and s.narration_text.strip()]
        if len(filled) >= len(storyboard) * 0.8:
            return storyboard  # mostly filled, trust it

        print(f"⚠️ Only {len(filled)}/{len(storyboard)} shots have narration_text — re-splitting from original narration.")
        import re
        # Split on sentence boundaries (period, newline, |, ।)
        sentences = [s.strip() for s in re.split(r'[।\.\n\|]+', narration) if s.strip()]

        n_shots = len(storyboard)
        n_sents = len(sentences)

        if n_sents >= n_shots:
            # More sentences than shots — group sentences into shots
            per_shot = n_sents / n_shots
            for i, shot in enumerate(storyboard):
                start = int(i * per_shot)
                end = int((i + 1) * per_shot)
                shot.narration_text = ' '.join(sentences[start:end])
        else:
            # Fewer sentences than shots — assign one sentence per shot, empty for extras
            for i, shot in enumerate(storyboard):
                shot.narration_text = sentences[i] if i < n_sents else ''

        return storyboard

    async def __call__(
        self,
        narration: str,
        user_requirement: str,
        style: str,
        characters: Optional[List[CharacterInScene]] = None,
        character_portraits_registry: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    ) -> str:
        """Run narration-driven pipeline. Narration and visuals stay in sync."""
        if characters is None:
            characters = await self.extract_characters(script=narration)

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

        storyboard_path = os.path.join(self.working_dir, "storyboard.json")
        if os.path.exists(storyboard_path):
            with open(storyboard_path, "r", encoding="utf-8") as f:
                storyboard = [ShotBriefDescription.model_validate(s) for s in json.load(f)]
            print(f"🚀 Loaded {len(storyboard)} shot brief descriptions from existing file.")
        else:
            print("🔍 Designing storyboard from narration...")
            storyboard = await self.storyboard_artist.design_storyboard_from_narration(
                narration=narration,
                characters=characters,
                user_requirement=user_requirement,
                style=style,
            )
            # Validate narration_text coverage — LLM sometimes leaves them null
            storyboard = self._fix_narration_text(storyboard, narration)
            with open(storyboard_path, "w", encoding="utf-8") as f:
                json.dump([s.model_dump() for s in storyboard], f, ensure_ascii=False, indent=4)
            print(f"✅ Designed storyboard and saved to {storyboard_path}.")

        for shot_brief in storyboard:
            self.shot_desc_events[shot_brief.idx] = asyncio.Event()

        shot_descriptions = await self.decompose_visual_descriptions(
            shot_brief_descriptions=storyboard,
            characters=characters,
        )

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

        final_video_path = os.path.join(self.working_dir, "final_video.mp4")
        if os.path.exists(final_video_path):
            print(f"🚀 Skipped final assembly, already exists.")
            return final_video_path

        print("🎬 Assembling final narrated video...")
        synced_clips = []
        for sd in shot_descriptions:
            vpath = os.path.join(self.working_dir, "shots", f"{sd.idx}", "video.mp4")
            npath = os.path.join(self.working_dir, "shots", f"{sd.idx}", "narration.wav")
            if not os.path.exists(vpath):
                logging.warning(f"Shot {sd.idx} video missing, skipping.")
                continue

            vclip = VideoFileClip(vpath).without_audio()
            narr_dur = self._shot_durations.get(sd.idx, vclip.duration)

            if vclip.duration > narr_dur:
                # Video longer than narration: trim video, add fade-out transition
                # for the surplus so it acts as a visual transition
                surplus = vclip.duration - narr_dur
                transition_dur = min(surplus, 1.5)  # fade-out over up to 1.5s
                vclip = vclip.with_duration(narr_dur + surplus)
                vclip = vclip.with_effects([FadeOut(transition_dur)])
                vclip = vclip.with_duration(narr_dur)
            elif vclip.duration < narr_dur:
                # Video shorter than narration: freeze last frame for remaining time
                last_frame = vclip.get_frame(vclip.duration - 0.05)
                from moviepy import ImageClip
                freeze = ImageClip(last_frame).with_duration(narr_dur - vclip.duration)
                freeze = freeze.with_effects([FadeOut(min(narr_dur - vclip.duration, 1.0))])
                vclip = concatenate_videoclips([vclip, freeze])

            # Attach narration audio to this clip
            if os.path.exists(npath):
                try:
                    aclip = AudioFileClip(npath)
                    if aclip.duration > vclip.duration:
                        aclip = aclip.with_duration(vclip.duration)
                    vclip = vclip.with_audio(aclip)
                except Exception as e:
                    logging.warning(f"Shot {sd.idx} audio mux failed: {e}")

            synced_clips.append(vclip)

        if not synced_clips:
            print("❌ No videos generated.")
            return ""

        final_video = concatenate_videoclips(synced_clips)
        final_video.write_videofile(final_video_path, codec="libx264", preset="medium")
        final_video.close()
        for c in synced_clips:
            c.close()
        print(f"☑️ Final narrated video saved to {final_video_path}.")
        return final_video_path
