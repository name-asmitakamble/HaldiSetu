"""
Split a folder-per-class image dataset into train/val/test (70/15/15), removing exact duplicates
first so the same image can never appear in two splits (data leakage).

Input layout :  RAW_DIR/<class_name>/*.jpg|png
Output layout:  OUT_DIR/{train,val,test}/<class_name>/...

Usage:  python ml/split_dataset.py data/raw data/turmeric
"""
import hashlib
import random
import shutil
import sys
from pathlib import Path

EXT = {".jpg", ".jpeg", ".png"}
SEED = 42


def main(raw, out):
    raw, out = Path(raw), Path(out)
    rnd = random.Random(SEED)
    summary = {}
    for cls in sorted(p for p in raw.iterdir() if p.is_dir()):
        seen, files = set(), []
        for f in sorted(cls.rglob("*")):
            if f.suffix.lower() not in EXT:
                continue
            h = hashlib.md5(f.read_bytes()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            files.append(f)
        rnd.shuffle(files)
        n = len(files)
        a, b = int(n * 0.70), int(n * 0.85)
        parts = {"train": files[:a], "val": files[a:b], "test": files[b:]}
        for split, items in parts.items():
            d = out / split / cls.name
            d.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(items):
                shutil.copy2(f, d / f"{cls.name}_{i:04d}{f.suffix.lower()}")
        summary[cls.name] = {k: len(v) for k, v in parts.items()}
    print(f"{'class':<20}{'train':>7}{'val':>6}{'test':>6}")
    for c, s in summary.items():
        print(f"{c:<20}{s['train']:>7}{s['val']:>6}{s['test']:>6}")
    print("\nKeep the test split untouched until the final evaluation.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
