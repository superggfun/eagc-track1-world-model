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

The v0.9 visual sequence smoke test does not download images. You can use different angles of the same room, or different crops of a local indoor photo. You can also pass another local directory with:

```powershell
python main.py --env visual_sequence --image-dir path\to\sequence --max-frames 3 --validate
```

This is not ProcTHOR, AI2-THOR, official runtime integration, or model training.
