Place a local bedroom scene image at:

```text
assets/test_images/bedroom.png
```

The v0.5 vision smoke path does not download images. You can also pass another local image path with:

```powershell
python tools/test_qwen_vision_call.py --image-path path\to\image.png
python main.py --vision --image-path path\to\image.png --validate
```
