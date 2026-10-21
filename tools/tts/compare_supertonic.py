"""Synthesize one sentence with Supertonic (fixed random seed) and save raw samples.
usage: compare_supertonic.py HELPER_DIR ONNX_DIR STYLE_JSON OUT.npy
Run once with the original models (new onnxruntime) and once with the
downgraded ones (onnxruntime 1.14.1), then compare the two .npy files.
"""
import sys

import numpy as np

sys.path.insert(0, sys.argv[1])
import helper  # noqa: E402
import onnxruntime as ort  # noqa: E402

np.random.seed(1234)
onnx_dir = sys.argv[2]
opts = ort.SessionOptions()
tts = helper.TextToSpeech(helper.load_cfgs(onnx_dir), helper.load_text_processor(onnx_dir),
                          *helper.load_onnx_all(onnx_dir, opts, ["CPUExecutionProvider"]))
style = helper.load_voice_style([sys.argv[3]])
wav, dur = tts("Excellent! That fork wins the queen.", "en", style, 4)
np.save(sys.argv[4], wav[0])
print("onnxruntime", ort.__version__, "samples", wav.shape[1])
