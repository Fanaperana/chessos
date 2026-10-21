# Text-to-speech on the R36S: benchmark

Measured on a K36 R36S clone running ChessOS (ArkOS-K36): 4× Cortex-A35 at
1296 MHz (`performance` governor), **736 MB RAM, ~511 MB free**, Python 3.7.5.
Run it yourself with `.\setup.ps1 ttsbench -Drive <EASYROMS letter>`, then
**Ports → TTS Benchmark** on the handheld. Source: [`tools/tts/`](../tools/tts).

RTF = synthesis time ÷ audio length (below 1.0 = faster than speech).

| Engine | Model load | "Knight takes e5, check." | RTF once loaded | Peak memory |
|---|---|---|---|---|
| espeak-ng 1.49 (system) | - | 0.3 s | 0.02 | 6 MB |
| Piper `en_US-lessac-low` | ~4.5 s | 7.6 s incl. load | **~0.9** | 128-180 MB |
| Piper `en_US-amy-low` | ~4.5 s | 7.2 s incl. load | ~0.9 | 180-194 MB |
| Piper `en_US-lessac-medium` | ~4.5 s | 7.4 s incl. load | ~1.2 | 194-215 MB |
| Supertonic, 2 steps | 17.2 s (import + load) | 4.1 s | 1.36-1.61 | 464 MB |
| Supertonic, 4 steps | (same) | 5.0 s | 1.79-1.98 | 468 MB |
| Supertonic, 8 steps | (same) | 7.4 s | 2.64-2.92 | 468 MB |

Piper's "RTF once loaded" comes from one process speaking all three test
sentences (12 s of audio in 15.7 s total, including one ~4.5 s model load).

## Notes

- **Supertonic** needed a model fix to run at all: ArkOS's Python 3.7 caps
  onnxruntime at 1.14.1 (IR 8 / opset 18) while the models are IR 9 / opset 19.
  [`downgrade_onnx.py`](../tools/tts/downgrade_onnx.py) relabels them; output is
  identical to the originals (correlation 1.000000, max sample difference 0.00014).
  Even so it uses 464 of the 511 MB free and is slower than real time.
- **Phonon** (Gradium) is closed / private beta with a per-device licence, and at
  ~100M parameters and up to ~500 MB it would hit the same memory wall.
- **Kokoro-82M** is too heavy for the device but excellent on a PC (~5× real time),
  so it pre-renders every fixed ChessOS line.

## Decision

1. **Fixed lines** (lessons, feedback, squares, piece names): **Kokoro** on the PC,
   shipped as WAV clips (Apache-2.0). Done.
2. **Live sentences** (future coach): **Piper `en_US-lessac-low`** as a background
   process loaded once at start-up, so a sentence is ready in about the time it
   takes to say it. Prefer pre-rendered phrase-bank clips wherever possible.
3. **espeak-ng** stays as the instant fallback for anything unexpected.
