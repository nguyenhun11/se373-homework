---
name: summarize-yt
description: Transcribe a YouTube video then summarize it in concise Vietnamese bullet points. Use when user wants to summarize, tóm tắt, or get key points from a YouTube URL.
---

# Summarize YouTube Video

Fetch the transcript from a YouTube URL using yt-dlp, read it, then write a concise Vietnamese summary directly.

## Workflow

### Step 1 — Ensure yt-dlp

```bash
which yt-dlp || brew install yt-dlp
```

### Step 2 — Download transcript

Try manual subtitles first, fall back to auto-generated:

```bash
mkdir -p tmp
yt-dlp --skip-download --write-subs --write-auto-subs \
  --sub-langs "en,vi" --convert-subs srt \
  --no-playlist -o "tmp/%(id)s.%(ext)s" "<URL>"
```

This outputs files like `tmp/<video_id>.en.srt` or `tmp/<video_id>.vi.srt`.

If no subtitle files are produced (private video, subtitles disabled), tell the user and stop.

### Step 3 — Convert SRT to plain text

Strip timecodes and blank lines from the SRT:

```bash
grep -v "^[0-9]*$" tmp/<video_id>.<lang>.srt \
  | grep -v "^[0-9][0-9]:.*-->" \
  | grep -v "^$" \
  > tmp/<video_id>.txt
```

### Step 4 — Summarize (agent task)

Read `tmp/<video_id>.txt`, then write a concise Vietnamese summary:
- Dạng bullet points ngắn gọn
- Chỉ giữ ý chính, bỏ chi tiết thừa

## Notes

- Prefer `vi` subtitles when available; otherwise use `en`
- Auto-generated subtitles are usually accurate enough for summarization
- No audio download, no model inference — transcript fetch is fast
