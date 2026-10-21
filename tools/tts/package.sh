#!/bin/bash
# Assemble the R36S TTS benchmark port from the files fetch.sh downloaded.
#   package.sh DOWNLOAD_DIR REPO_DIR OUT_DIR
# OUT_DIR gets: "TTS Benchmark.sh" + ttsbench/ (copy both into EASYROMS/ports/)
set -e
DL=${1:?download dir}; REPO=${2:?repo}; OUT=${3:?out dir}
B="$OUT/ttsbench"
rm -rf "$OUT"; mkdir -p "$B"/{out,voices,pylib,supertonic/py}

echo "piper"
tar xzf "$DL/piper/piper_linux_aarch64.tar.gz" -C "$B"
cp "$DL"/voices/*.onnx "$DL"/voices/*.onnx.json "$B/voices/"

echo "python packages (cp37 aarch64)"
for w in "$DL"/wheels/*.whl; do (cd "$B/pylib" && python3 -m zipfile -e "$w" .); done
rm -rf "$B"/pylib/*.dist-info

echo "supertonic"
[ -f "$DL/supertonic/onnx18/vocoder.onnx" ] || { echo "run verify_downgrade.sh first"; exit 1; }
cp -r "$DL/supertonic/voice_styles" "$DL/supertonic/LICENSE" "$B/supertonic/"
cp -r "$DL/supertonic/onnx18" "$B/supertonic/onnx"   # IR 8 / opset 18 for onnxruntime 1.14
# Python 3.7: postpone evaluation of list[str]-style annotations
{ echo "from __future__ import annotations"; cat "$DL/supertonic/py/helper.py"; } > "$B/supertonic/py/helper.py"

cp "$REPO/tools/tts/bench.py" "$B/bench.py"
cat > "$OUT/TTS Benchmark.sh" <<'EOF'
#!/bin/bash
# ChessOS TTS benchmark - results in ports/ttsbench/results.txt
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)/ttsbench"
sudo chmod 666 /dev/tty1 2>/dev/null
printf "\033c" > /dev/tty1
chmod +x "$DIR/piper/piper" "$DIR/piper/espeak-ng" "$DIR/piper/piper_phonemize" 2>/dev/null
cd "$DIR" && python3 -u bench.py > "$DIR/console.log" 2>&1
sudo cp "$DIR/results.txt" /boot/chessos_tts_results.txt 2>/dev/null
sleep 5
printf "\033c" > /dev/tty1
EOF
find "$OUT" -name "*.sh" -o -name "*.py" | while read -r f; do sed -i 's/\r$//' "$f"; done
du -sh "$B"
echo PACKAGE_OK
