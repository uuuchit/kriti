# https://ai.google.dev/gemini-api/docs/speech-generation

import logging
import asyncio
from typing import Optional
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from tenacity import retry, stop_after_attempt

from interfaces.audio_output import AudioOutput
from utils.retry import after_func
from utils.rate_limiter import RateLimiter


class AudioGeneratorGoogleAPI:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-preview-tts",
        voice_name: str = "Kore",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.model = model
        self.voice_name = voice_name
        self.rate_limiter = rate_limiter
        self.client = genai.Client(api_key=api_key)

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_single_audio(
        self,
        text: str,
        voice_name: Optional[str] = None,
        **kwargs,
    ) -> AudioOutput:
        """Generate speech audio from text using Google GenAI TTS."""
        if not text or not text.strip():
            raise ValueError("Text for TTS cannot be empty")

        voice = voice_name or self.voice_name
        logging.info(f"Calling {self.model} for TTS (voice={voice})...")

        if self.rate_limiter:
            await self.rate_limiter.acquire()

        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                response = await self.client.aio.models.generate_content(
                    model=self.model,
                    contents=text.strip(),
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=voice,
                                )
                            )
                        ),
                    ),
                )
                break
            except ClientError as e:
                if e.status_code == 429 and attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    logging.warning(
                        f"Rate limit hit (429), retrying in {wait_time}s... "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise

        if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
            finish_reason = (
                getattr(response.candidates[0], "finish_reason", "unknown")
                if response.candidates
                else "no_candidates"
            )
            logging.error(f"TTS blocked (finish_reason={finish_reason}). Text: {text[:80]}...")
            raise ValueError(f"TTS blocked by API (reason: {finish_reason})")

        part = response.candidates[0].content.parts[0]
        if not part.inline_data or not part.inline_data.data:
            logging.error("TTS returned no audio data")
            raise ValueError("No audio data in TTS response")

        pcm_data = part.inline_data.data
        return AudioOutput(
            fmt="bytes",
            ext="wav",
            data=pcm_data,
            sample_rate=24000,
            channels=1,
            sample_width=2,
        )
