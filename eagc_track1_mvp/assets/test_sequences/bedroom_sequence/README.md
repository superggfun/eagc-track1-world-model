Place local visual sequence frames here using deterministic names:

```text
frame_000.png
frame_001.png
frame_002.png
```

The v0.5.1 visual sequence smoke test does not download images. You can also pass another local directory with:

```powershell
python main.py --env visual_sequence --image-dir path\to\sequence --max-steps 3 --validate
```
