"""Download the chess engine and live-voice engine ChessOS bundles (not stored in git).

R36S (linux-aarch64, ArkOS = Ubuntu 19.10):
  Stockfish 9   Ubuntu's own arm64 package (GPL-3), matches ArkOS's libraries
  Piper         rhasspy/piper 2023.11.14-2 aarch64 build (MIT)
PC (windows, for development/testing only):
  Stockfish 19  official build      Piper 2023.11.14-2 windows build
Voice: Piper en_US-lessac-low (dataset licence: non-commercial research - fine
for your own device, which is why it's downloaded here instead of committed).

Output: device/chessos/bin/<platform>/...  and device/chessos/assets/piper/
"""
import io
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "device", "chessos")
CACHE = os.path.join(ROOT, "work", "downloads")

SF_DEB = "http://old-releases.ubuntu.com/ubuntu/pool/universe/s/stockfish/stockfish_9-2_arm64.deb"
SF_WIN = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip"
PIPER_ARM = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"
PIPER_WIN = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
VOICE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low/en_US-lessac-low"


def get(url):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, url.rsplit("/", 1)[1])
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        print("  downloading", url.rsplit("/", 1)[1])
        req = urllib.request.Request(url, headers={"User-Agent": "ChessOS-build"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path + ".part", "wb") as f:
            shutil.copyfileobj(r, f)
        os.replace(path + ".part", path)
    return path


def deb_member(deb, wanted):
    """Read one file out of a .deb (ar archive -> data.tar.xz) with the stdlib only."""
    with open(deb, "rb") as f:
        data = f.read()
    assert data[:8] == b"!<arch>\n"
    pos = 8
    while pos < len(data):
        name = data[pos:pos + 16].decode().strip().rstrip("/")
        size = int(data[pos + 48:pos + 58].decode().strip())
        body = data[pos + 60:pos + 60 + size]
        if name.startswith("data.tar"):
            with tarfile.open(fileobj=io.BytesIO(body)) as t:
                for m in t.getmembers():
                    if m.name.lstrip("./") == wanted:
                        return t.extractfile(m).read()
        pos += 60 + size + (size & 1)
    raise SystemExit("%s not found in %s" % (wanted, deb))


def main():
    arm = os.path.join(APP, "bin", "linux-aarch64")
    win = os.path.join(APP, "bin", "windows")
    os.makedirs(arm, exist_ok=True)

    print("Stockfish 9 (arm64, Ubuntu package)")
    sf = deb_member(get(SF_DEB), "usr/games/stockfish")
    with open(os.path.join(arm, "stockfish"), "wb") as f:
        f.write(sf)

    print("Piper (aarch64)")
    with tarfile.open(get(PIPER_ARM)) as t:
        dst = os.path.join(arm, "piper")
        if os.path.isdir(dst):
            shutil.rmtree(dst)
        t.extractall(arm, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))  # arm/piper/

    print("Voice en_US-lessac-low")
    vdir = os.path.join(APP, "assets", "piper")
    os.makedirs(vdir, exist_ok=True)
    for ext in (".onnx", ".onnx.json"):
        shutil.copyfile(get(VOICE + ext), os.path.join(vdir, "en_US-lessac-low" + ext))

    if sys.platform == "win32" or "--windows" in sys.argv:
        print("PC builds (Windows, for testing)")
        os.makedirs(win, exist_ok=True)
        with zipfile.ZipFile(get(SF_WIN)) as z:
            exe = [n for n in z.namelist() if n.endswith(".exe")][0]
            with open(os.path.join(win, "stockfish.exe"), "wb") as f:
                f.write(z.read(exe))
        with zipfile.ZipFile(get(PIPER_WIN)) as z:
            if os.path.isdir(os.path.join(win, "piper")):
                shutil.rmtree(os.path.join(win, "piper"))
            z.extractall(win)
    for base, _, files in os.walk(os.path.join(APP, "bin")):
        for f in files:
            if f in ("stockfish", "piper", "espeak-ng", "piper_phonemize"):
                os.chmod(os.path.join(base, f), 0o755)
    print("engines ready in", os.path.relpath(os.path.join(APP, "bin"), ROOT))


if __name__ == "__main__":
    main()
