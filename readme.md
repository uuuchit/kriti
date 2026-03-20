# Kriti

Narration-to-video pipeline. Takes Hindi narration text and generates synced portrait (9:16) video with TTS audio using Google Gemini APIs (Imagen, Veo, TTS).

## Install

```bash
# Requires Python 3.10+ and uv
pip install uv
git clone git@github.com:uuuchit/kriti.git
cd kriti
uv sync
```

Create a `.env` file:

```
GEMINI_API_KEY=<your-gemini-api-key>
```

## Run

Edit `main_narration2video.py` with your narration text, style, and requirements, then:

```bash
uv run python -u main_narration2video.py
```

Output will be at `.working_dir/narration2video/final_video.mp4`.
