#!/bin/bash
# Run ChessOS on the PC with an autopilot script and convert screenshots to PNG.
# usage: tools/pc_test.sh "0.6,shot:splash,quit" [fresh]
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(cygpath -m "${CHESSOS_TEST_DIR:-$ROOT/build/test}")"
[ "$2" = "fresh" ] && rm -rf "$OUT"
mkdir -p "$OUT/shots"
cd "$ROOT/device/chessos"
CHESSOS_UNLOCK=${CHESSOS_UNLOCK:-0} CHESSOS_SCALE=1 CHESSOS_SAVE="$OUT/save.json" CHESSOS_SHOTS="$OUT/shots" CHESSOS_FPS=${CHESSOS_FPS:-1} \
  CHESSOS_AUTOPILOT="$1" timeout 120 "$ROOT/.venv/Scripts/python.exe" main.py 2>&1 | grep -v UserWarning
"$ROOT/.venv/Scripts/python.exe" -c "
import glob,os
from PIL import Image
for f in glob.glob(os.path.join(r'$OUT','shots','*.bmp')):
    Image.open(f).save(f[:-4]+'.png'); os.remove(f)
"
ls "$OUT/shots"
if [ -f crash.log ]; then tail -15 crash.log; rm crash.log; fi
