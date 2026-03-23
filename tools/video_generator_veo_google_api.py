import logging
from typing import List, Optional
import asyncio
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt
from interfaces.video_output import VideoOutput
from utils.rate_limiter import RateLimiter
from utils.retry import after_func

# https://ai.google.dev/gemini-api/docs/video-generation?hl=zh-cn


class VideoGeneratorVeoGoogleAPI:
    def __init__(
        self,
        api_key: str,
        t2v_model: str = "veo-3.1-generate-preview",
        ff2v_model: str = "veo-3.1-generate-preview",
        flf2v_model: str = "veo-3.1-generate-preview",
        aspect_ratio: str = "16:9",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.api_key = api_key
        self.t2v_model = t2v_model
        self.ff2v_model = ff2v_model
        self.flf2v_model = flf2v_model
        self.default_aspect_ratio = aspect_ratio
        self.rate_limiter = rate_limiter

        self.client = genai.Client(
            api_key=api_key,
        )
    
    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_single_video(
        self,
        prompt: str,
        reference_image_paths: List[str],
        resolution: str = "720p",
        aspect_ratio: str = None,
        duration: int = 8,
    ) -> VideoOutput:

        params = {
            "prompt": prompt,
        }
        config_params = {
            "resolution": resolution,
            "aspect_ratio": aspect_ratio or self.default_aspect_ratio,
            "duration_seconds": duration,
        }
        if len(reference_image_paths) == 0:
            params["model"] = self.t2v_model
        elif len(reference_image_paths) == 1:
            params["model"] = self.ff2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
        elif len(reference_image_paths) == 2:
            params["model"] = self.flf2v_model
            params["image"] = types.Image.from_file(location=reference_image_paths[0])
            config_params["last_frame"] = types.Image.from_file(location=reference_image_paths[1])
        else:
            raise ValueError("The number of reference images must be no more than 2")

        logging.info(f"Calling {params['model']} to generate video...")
        print(f"  [VEO] prompt={prompt[:200]}...")
        print(f"  [VEO] refs={len(reference_image_paths)} duration={duration}s aspect={config_params['aspect_ratio']}")

        # Apply rate limiting if configured
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # Retry logic for rate limit errors
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                operation = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.client.models.generate_videos,
                        **params,
                        config=types.GenerateVideosConfig(**config_params),
                    ),
                    timeout=60,
                )
                break
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    logging.warning(f"generate_videos timed out, retrying... ({attempt+1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    raise RuntimeError("generate_videos timed out after all retries")
            except ClientError as e:
                if hasattr(e, 'status_code') and e.status_code == 429 and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(f"Rate limit hit (429), retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                elif '429' in str(e) and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(f"Rate limit hit, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        max_poll = 300  # 5 min timeout
        elapsed = 0
        while not operation.done:
            await asyncio.sleep(5)
            elapsed += 5
            if elapsed >= max_poll:
                raise RuntimeError(f"Video generation timed out after {max_poll}s")
            try:
                operation = await asyncio.wait_for(
                    asyncio.to_thread(self.client.operations.get, operation),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                raise RuntimeError("Veo poll request timed out (30s)")

        # Check if operation completed successfully
        if operation.error:
            error_msg = f"Video generation failed: {operation.error}"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        if not operation.response:
            error_msg = "Video generation completed but no response received"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        if not hasattr(operation.response, 'generated_videos') or not operation.response.generated_videos:
            if reference_image_paths:
                logging.warning("Veo returned no videos with reference images — retrying as text-to-video...")
                return await self.generate_single_video(
                    prompt=prompt,
                    reference_image_paths=[],
                    resolution=resolution,
                    aspect_ratio=aspect_ratio,
                    duration=duration,
                )
            error_msg = "Video generation completed but no videos were generated"
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        generated_video = operation.response.generated_videos[0]
        await asyncio.to_thread(self.client.files.download, file=generated_video.video)

        video_output = VideoOutput(
            fmt="bytes",
            ext="mp4",
            data=generated_video.video.video_bytes,
        )
        return video_output
