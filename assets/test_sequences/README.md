# Local Visual Test Sequences

Place local multi-frame test images under a sequence directory such as:

```text
assets/test_sequences/bedroom_sequence/
  frame_000.jpg
  frame_001.jpg
  frame_002.jpg
```

Use local photos, different angles of the same indoor scene, or cropped variants of a local room image. The v0.9.1 validation used three Pexels bedroom images as local smoke-test resources.

Frame images are intentionally ignored by git. Do not commit `frame_*.jpg`, `frame_*.png`, `frame_*.jpeg`, or `frame_*.webp` files.

v0.9 is a visual sequence interface and incremental world-model update smoke test. It is not ProcTHOR, AI2-THOR, official runtime integration, or model training.
