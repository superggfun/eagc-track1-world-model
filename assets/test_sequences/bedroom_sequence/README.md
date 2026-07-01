Place local visual sequence frames here using deterministic names:

```text
frame_000.jpg
frame_001.jpg
frame_002.jpg
```

PNG files are also supported:

```text
frame_000.png
frame_001.png
frame_002.png
```

The v0.9 visual sequence smoke test does not download images. You can use different angles of the same room, different crops of a local indoor photo, or locally downloaded free images such as Pexels bedroom photos. You can also pass another local directory with:

```powershell
python main.py --env visual_sequence --image-dir path\to\sequence --max-frames 3 --validate
```

Frame files in this directory are local test resources and are ignored by git. Do not commit `frame_*.jpg`, `frame_*.png`, `frame_*.jpeg`, or `frame_*.webp`.

The v0.9.1 validation used three Pexels bedroom frames and passed with `processed_frames=3`, `qwen_call_count=3`, `fallback_used=False`, `vision_parse_success=True`, `object_count=15`, and `relation_count=23`. Object and relation counts can vary slightly across real Qwen vision runs.

This is not ProcTHOR, AI2-THOR, official runtime integration, or model training.
