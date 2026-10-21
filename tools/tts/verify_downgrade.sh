#!/bin/bash
# Downgrade Supertonic's ONNX models and prove the output is unchanged.
#   verify_downgrade.sh DOWNLOAD_DIR REPO_DIR
set -e
DL=${1:?}; REPO=${2:?}
S="$DL/supertonic"
OLD=$HOME/ttsvenv            # onnxruntime 1.14.1 (what the R36S gets)
NEW=$HOME/ttsvenv-new        # current onnxruntime, runs the original models
[ -x "$NEW/bin/python" ] || { python3 -m venv "$NEW"; "$NEW/bin/pip" install -q onnxruntime "numpy<2"; }
"$OLD/bin/pip" install -q "onnx==1.16.2" > /dev/null
echo "downgrading:"
"$OLD/bin/python" "$REPO/tools/tts/downgrade_onnx.py" "$S/onnx" "$S/onnx18"
for f in tts.json unicode_indexer.json; do cp "$S/onnx/$f" "$S/onnx18/"; done
H=$HOME/sthelper; mkdir -p "$H"
{ echo "from __future__ import annotations"; cat "$S/py/helper.py"; } > "$H/helper.py"
"$NEW/bin/python" "$REPO/tools/tts/compare_supertonic.py" "$H" "$S/onnx" "$S/voice_styles/M1.json" /tmp/st_new.npy
"$OLD/bin/python" "$REPO/tools/tts/compare_supertonic.py" "$H" "$S/onnx18" "$S/voice_styles/M1.json" /tmp/st_old.npy
"$OLD/bin/python" - <<'EOF'
import numpy as np
a, b = np.load("/tmp/st_new.npy"), np.load("/tmp/st_old.npy")
n = min(len(a), len(b))
diff = np.abs(a[:n] - b[:n]).max()
corr = np.corrcoef(a[:n], b[:n])[0, 1]
print("length new/old: %d / %d   max sample difference %.6f   correlation %.6f" % (len(a), len(b), diff, corr))
print("IDENTICAL_ENOUGH" if len(a) == len(b) and corr > 0.999 else "DIFFERENT")
EOF
