#!/bin/bash
# Dry-run the TTS benchmark on x86 Linux/WSL with the same engine versions.
#   dryrun_x86.sh DOWNLOAD_DIR PKG_DIR
set -e
DL=${1:?}; PKG=${2:?}; shift 2
T=$HOME/ttsbench-x86
rm -rf "$T"; mkdir -p "$T/out"
cp "$PKG/ttsbench/bench.py" "$T/"
cp -r "$PKG/ttsbench/voices" "$PKG/ttsbench/supertonic" "$T/"
mkdir -p "$T/pylib"   # x86: packages come from the venv instead
[ -s "$DL/piper_linux_x86_64.tar.gz" ] || curl -L --fail -s -o "$DL/piper_linux_x86_64.tar.gz" \
  https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz
tar xzf "$DL/piper_linux_x86_64.tar.gz" -C "$T"
V=$HOME/ttsvenv
if [ ! -x "$V/bin/python" ]; then
  python3 -m venv "$V"
  "$V/bin/pip" install -q "onnxruntime==1.14.1" "numpy<2"
fi
cd "$T" && BENCH_PLAY=0 "$V/bin/python" -u bench.py "$@"
