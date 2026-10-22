#!/usr/bin/env python3
"""
Categorize images by face count using YOLOv8.
Moves images into:
  - single_face/    (exactly 1 face detected)
  - multiple_faces/ (2+ faces detected)
  - no_face/        (0 faces detected)

Usage:
  python categorize_faces.py <input_dir> [--confidence 0.5] [--move]
"""

import argparse
import shutil
from pathlib import Path

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}


def load_model():
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "ultralytics is not installed.\n"
            "Run: pip install ultralytics"
        )
    # yolov8n-face is a face-specific model; falls back to downloading on first run
    model = YOLO("yolov8n-face.pt")
    return model


def categorize_images(input_dir: Path, confidence: float, move: bool):
    model = load_model()

    # Create output subdirectories
    dirs = {
        "single_face": input_dir / "single_face",
        "multiple_faces": input_dir / "multiple_faces",
        "no_face": input_dir / "no_face",
    }
    for d in dirs.values():
        d.mkdir(exist_ok=True)

    images = [p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]

    if not images:
        print(f"No images found in {input_dir}")
        return

    print(f"Processing {len(images)} image(s) with confidence threshold {confidence}...\n")

    counts = {"single_face": 0, "multiple_faces": 0, "no_face": 0}

    for img_path in images:
        results = model(str(img_path), conf=confidence, verbose=False)
        # results[0].boxes contains all detections for the image
        num_faces = len(results[0].boxes)

        if num_faces == 1:
            category = "single_face"
        elif num_faces >= 2:
            category = "multiple_faces"
        else:
            category = "no_face"

        dest = dirs[category] / img_path.name

        if move:
            shutil.move(str(img_path), dest)
            action = "Moved"
        else:
            shutil.copy2(str(img_path), dest)
            action = "Copied"

        counts[category] += 1
        print(f"[{num_faces} face(s)] {action}: {img_path.name} -> {category}/")

    print(f"\nDone.")
    print(f"  single_face:    {counts['single_face']}")
    print(f"  multiple_faces: {counts['multiple_faces']}")
    print(f"  no_face:        {counts['no_face']}")


def main():
    parser = argparse.ArgumentParser(description="Categorize images by face count using YOLOv8.")
    parser.add_argument("input_dir", type=Path, help="Directory containing images to process")
    parser.add_argument(
        "--confidence", "-c", type=float, default=0.5,
        help="Detection confidence threshold (default: 0.5)"
    )
    parser.add_argument(
        "--move", action="store_true",
        help="Move files instead of copying them (default: copy)"
    )
    args = parser.parse_args()

    if not args.input_dir.is_dir():
        raise SystemExit(f"Error: '{args.input_dir}' is not a valid directory.")

    categorize_images(args.input_dir, args.confidence, args.move)


if __name__ == "__main__":
    main()
