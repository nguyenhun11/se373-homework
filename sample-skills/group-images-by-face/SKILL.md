---
name: group-images-by-face
description: Categorize images in a directory by number of faces detected (single_face, multiple_faces, no_face) using YOLOv8. Use when user wants to sort, group, or organize images by face count.
---

# Group Images by Face Count

Run `categorize_faces.py` against a user-supplied directory to sort images into `single_face/`, `multiple_faces/`, and `no_face/` subdirectories using YOLOv8 face detection.

The script lives at:
```
<skill_dir>/scripts/categorize_faces.py
```

## Workflow

### Step 1 — Confirm input directory

Ask the user for the target directory if not already provided. Example:
> "Which folder do you want to categorize?"

### Step 2 — Ensure dependency

```bash
pip show ultralytics > /dev/null 2>&1 || pip install ultralytics
```

### Step 3 — Run the script

Resolve the script path relative to `<skill_dir>`. Default (copy files, keep originals):
```bash
python "<skill_dir>/scripts/categorize_faces.py" "<input_dir>"
```

Move files instead of copying:
```bash
python "<skill_dir>/scripts/categorize_faces.py" "<input_dir>" --move
```

Custom confidence threshold (default is 0.5):
```bash
python "<skill_dir>/scripts/categorize_faces.py" "<input_dir>" --confidence 0.4
```

### Step 4 — Report results

After the script finishes, report the summary counts to the user:
- How many images landed in each category
- Where the output subdirectories are located
- Mention the model used (`yolov8n-face.pt`) and that it auto-downloads on first run

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--confidence` / `-c` | `0.5` | Detection confidence threshold (0.0–1.0) |
| `--move` | off | Move files instead of copying |

## Output structure

```
<input_dir>/
  single_face/       # exactly 1 face detected
  multiple_faces/    # 2 or more faces detected
  no_face/           # no faces detected
```

## Notes

- `yolov8n-face.pt` is downloaded automatically by `ultralytics` on first run (~6 MB)
- Supported formats: `.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.tiff`, `.tif`
- Lower confidence (e.g. `0.3`) catches more faces but may produce false positives
- Higher confidence (e.g. `0.7`) is more precise but may miss partially obscured faces
