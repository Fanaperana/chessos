"""Render the same lines in several Kokoro voices so you can pick one.
usage: kokoro_audition.py KOKORO_DIR OUT_DIR
"""
import os
import sys
import time

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

VOICES = ["af_heart", "af_bella", "af_nicole", "am_michael", "am_fenrir", "bf_emma", "bm_george"]
LINES = [
    "Welcome to Chess O S! Let's learn chess.",
    "Knight takes e5, check.",
    "Excellent! That fork wins the queen.",
]

kdir, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
k = Kokoro(os.path.join(kdir, "kokoro-v1.0.onnx"), os.path.join(kdir, "voices-v1.0.bin"))
for v in VOICES:
    t0 = time.time()
    parts = []
    for line in LINES:
        samples, sr = k.create(line, voice=v, speed=1.0, lang="en-gb" if v.startswith("b") else "en-us")
        parts += [samples, np.zeros(int(sr * 0.45), dtype=np.float32)]
    audio = np.concatenate(parts)
    sf.write(os.path.join(out, "kokoro_%s.wav" % v), audio, sr)
    print("%-11s %.1fs audio in %.1fs" % (v, len(audio) / sr, time.time() - t0))
