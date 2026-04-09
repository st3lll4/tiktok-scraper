"""
Merge individual video comment CSVs into one database file.
"""

from pathlib import Path

import pandas as pd


def merge_csvs(output_dir: str = "output", db_filename: str = "database.csv") -> Path:
    """
    Find all comments_*.csv files in output_dir and merge them into one
    database CSV. Each row gets a source_video column with the video ID.

    Returns the path to the merged database file.
    """
    output_path = Path(output_dir)
    csv_files = sorted(output_path.glob("comments_*.csv"))

    if not csv_files:
        print("[merger] No comment CSV files found in", output_dir)
        return output_path / db_filename

    frames = []
    for csv_file in csv_files:
        # Extract video ID from filename: comments_<video_id>.csv
        video_id = csv_file.stem.replace("comments_", "")
        df = pd.read_csv(csv_file, encoding="utf-8-sig")
        df["video_id"] = video_id
        frames.append(df)
        print(f"[merger] Loaded {len(df)} comments from {csv_file.name}")

    merged = pd.concat(frames, ignore_index=True)
    # Reorder columns for readability
    cols = ["video_id", "username", "comment", "reply_to", "timestamp"]
    cols = [c for c in cols if c in merged.columns]
    merged = merged[cols]

    db_path = output_path / db_filename
    merged.to_csv(db_path, index=False, encoding="utf-8-sig")
    print(f"[merger] Merged database: {len(merged)} total comments -> {db_path}")
    return db_path
