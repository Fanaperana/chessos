# ChessOS's own build steps. setup.ps1 build runs this hook (if the active
# app has one) before making the boot logo and dist\. Not copied to the card.
# Provided by setup.ps1: $Root, $WorkDir, Step, Run-Py
Step "Puzzle packs (Lichess puzzle database, CC0)"
Run-Py "$Root\tools\build_puzzles.py"
Step "Sprites and piece sets"
Run-Py "$Root\tools\build_assets.py"
Step "Voice clips (Kokoro, Apache-2.0) + sound effects"
# The repo ships finished clips; Kokoro is only downloaded when clips must be (re)made.
if (-not (Test-Path "$Root\device\chessos\assets\voice\engine.txt") -or $env:CHESSOS_TTS -eq "kokoro") {
  $kdir = Join-Path $WorkDir "kokoro"
  New-Item -ItemType Directory -Force $kdir | Out-Null
  foreach ($f in "kokoro-v1.0.onnx", "voices-v1.0.bin") {
    if (-not (Test-Path "$kdir\$f")) {
      Write-Host "  downloading $f"
      & curl.exe -L --fail -s -o "$kdir\$f" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f"
    }
  }
  $env:CHESSOS_KOKORO_DIR = $kdir
}
Run-Py "$Root\tools\build_audio.py"
Step "Chess engine + live voice (Stockfish, Piper)"
Run-Py "$Root\tools\fetch_engines.py"
