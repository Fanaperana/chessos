#!/bin/bash
# Download TTS engines/models for the R36S benchmark into $1 (default: ./tts-dl).
# Everything goes to its own folder; nothing is executed here.
set -e
OUT=${1:-tts-dl}
mkdir -p "$OUT"/{piper,voices,supertonic/onnx,supertonic/voice_styles,supertonic/py,wheels}
cd "$OUT"
get() { [ -s "$2" ] || curl -L --fail -s -S -o "$2" "$1"; echo "  $(du -h "$2" | cut -f1)  $2"; }

echo "Piper (rhasspy/piper 2023.11.14-2, aarch64)"
get https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz piper/piper_linux_aarch64.tar.gz
V=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US
for v in lessac/low/en_US-lessac-low lessac/medium/en_US-lessac-medium amy/low/en_US-amy-low; do
  n=$(basename $v)
  get "$V/$v.onnx" voices/$n.onnx
  get "$V/$v.onnx.json" voices/$n.onnx.json
done
get https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/MODEL_CARD voices/lessac.MODEL_CARD

echo "Supertonic (supertone-oss-archive/supertonic)"
S=https://huggingface.co/supertone-oss-archive/supertonic/resolve/main
for f in onnx/duration_predictor.onnx onnx/text_encoder.onnx onnx/vector_estimator.onnx onnx/vocoder.onnx \
         onnx/tts.json onnx/unicode_indexer.json voice_styles/M1.json voice_styles/F1.json LICENSE; do
  get "$S/$f" supertonic/$f
done
G=https://raw.githubusercontent.com/supertone-inc/supertonic/main/py
get $G/helper.py supertonic/py/helper.py
get $G/example_onnx.py supertonic/py/example_onnx.py

echo "Python 3.7 aarch64 wheels (for Supertonic on ArkOS)"
P=https://files.pythonhosted.org/packages
pyget() { url=$(curl -s "https://pypi.org/pypi/$1/$2/json" | python3 -c "import json,sys;print([u['url'] for u in json.load(sys.stdin)['urls'] if u['filename']=='$3'][0])"); get "$url" "wheels/$3"; }
pyget onnxruntime 1.14.1 onnxruntime-1.14.1-cp37-cp37m-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
pyget numpy 1.21.6 numpy-1.21.6-cp37-cp37m-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
echo FETCH_OK
