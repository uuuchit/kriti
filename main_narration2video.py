import asyncio
import csv
import sys
import os
from pipelines.narration2video_pipeline import Narration2VideoPipeline

CSV_PATH = "narrations.csv"  # columns: id, narration, style, requirement


async def run_one(row):
    rid = row["id"]
    print(f"\n{'='*60}\n🎬 Starting narration: {rid}\n{'='*60}")
    pipeline = Narration2VideoPipeline.init_from_config(
        config_path="configs/narration2video.yaml"
    )
    pipeline.working_dir = f".generations/{rid}"
    os.makedirs(pipeline.working_dir, exist_ok=True)
    await pipeline(
        narration=row["narration"],
        user_requirement=row.get("requirement", ""),
        style=row.get("style", ""),
    )
    print(f"✅ Done: {rid} → {pipeline.working_dir}/final_video.mp4")


async def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CSV_PATH
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} narrations from {path}")
    for row in rows:
        await run_one(row)


if __name__ == "__main__":
    asyncio.run(main())
