"""Audio output from TTS/audio generation."""

import wave
from typing import Literal, Union


class AudioOutput:
    """Holds raw PCM audio data and can save to WAV."""

    def __init__(
        self,
        fmt: Literal["bytes"],
        ext: str,
        data: bytes,
        sample_rate: int = 24000,
        channels: int = 1,
        sample_width: int = 2,
    ):
        self.fmt = fmt
        self.ext = ext
        self.data = data
        self.sample_rate = sample_rate
        self.channels = channels
        self.sample_width = sample_width

    @property
    def duration_sec(self) -> float:
        """Duration in seconds derived from PCM length."""
        if not self.data:
            return 0.0
        bytes_per_sample = self.channels * self.sample_width
        num_samples = len(self.data) // bytes_per_sample
        return num_samples / self.sample_rate

    def save(self, path: str) -> None:
        """Save PCM data as a WAV file."""
        with wave.open(path, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.sample_width)
            wf.setframerate(self.sample_rate)
            wf.writeframes(self.data)
