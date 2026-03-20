"""Helpers for extracting narration/dialogue text from shot audio descriptions."""

import re
from typing import Optional


def extract_narration_text(audio_desc: Optional[str]) -> str:
    """Extract text suitable for TTS from audio_desc.

    Narration is sacred — never truncate. Handles nested quotes by
    taking everything between the FIRST and LAST quote marks.
    """
    if not audio_desc or not audio_desc.strip():
        return ""

    text = audio_desc.strip()

    if text.upper().startswith("[SOUND EFFECT]"):
        return ""

    # Try to get content after [Speaker]/[Narrator] tag + colon
    speaker_match = re.search(r"\][^:]*:\s*(.+)", text, re.DOTALL)
    if speaker_match:
        content = speaker_match.group(1).strip()
        # Strip outermost quotes only (preserves nested quotes for TTS)
        if content.startswith('"') and content.endswith('"') and len(content) > 1:
            content = content[1:-1].strip()
        return content

    # "Narration: content"
    if "narration:" in text.lower():
        content = text.split(":", 1)[1].strip()
        if content.startswith('"') and content.endswith('"') and len(content) > 1:
            content = content[1:-1].strip()
        return content

    # Fallback
    if len(text) < 500 and "[" not in text:
        return text

    return ""
