"""Assemble dist/ for the SD card:  dist/EASYROMS/ports/...  and  dist/BOOT/...
Also writes dist/ChessOS-beta.zip. Scripts get Unix (LF) line endings.
"""
import os
import shutil
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV = os.path.join(ROOT, "device")
DIST = os.path.join(ROOT, "dist")
PORTS = os.path.join(DIST, "EASYROMS", "ports")

SKIP_DIRS = {"__pycache__", "save", "shots", "test"}
SKIP_FILES = {"crash.log", "log.txt", "boot_log.txt"}
LF_EXT = (".sh", ".py", ".txt", ".pgn", ".json", ".conf")


def copy_tree(src, dst):
    for base, dirs, files in os.walk(src):
        rel = os.path.relpath(base, src)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (rel == "puzzles" and d == "daily")
                   and not (rel == "bin" and d == "windows")]  # PC test engines stay on the PC
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            if f in SKIP_FILES or f.endswith(".pyc"):
                continue
            s, d = os.path.join(base, f), os.path.join(dst, rel, f)
            if f.endswith(LF_EXT) and "bin" not in rel.split(os.sep):
                with open(s, "rb") as fh:
                    data = fh.read().replace(b"\r\n", b"\n")
                with open(d, "wb") as fh:
                    fh.write(data)
            else:
                shutil.copyfile(s, d)


def write_lf(src, dst):
    with open(src, "rb") as fh:
        data = fh.read().replace(b"\r\n", b"\n")
    with open(dst, "wb") as fh:
        fh.write(data)


def main():
    if os.path.isdir(os.path.join(DIST, "EASYROMS")):
        shutil.rmtree(os.path.join(DIST, "EASYROMS"))
    os.makedirs(PORTS, exist_ok=True)
    copy_tree(os.path.join(DEV, "chessos"), os.path.join(PORTS, "chessos"))
    # build date: ChessOS treats any clock earlier than this as wrong (no RTC on the R36S)
    import datetime
    import json
    with open(os.path.join(PORTS, "chessos", "data", "build.json"), "w") as f:
        json.dump({"date": datetime.date.today().isoformat()}, f)
    os.makedirs(os.path.join(PORTS, "chessos", "puzzles", "daily"), exist_ok=True)
    for name in ("ChessOS.sh", "ChessOS Boot Mode.sh"):
        write_lf(os.path.join(DEV, name), os.path.join(PORTS, name))
    write_lf(os.path.join(DEV, "README.txt"), os.path.join(DIST, "README.txt"))
    zpath = os.path.join(DIST, "ChessOS-beta.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(DIST):
            for f in files:
                p = os.path.join(base, f)
                if p == zpath:
                    continue
                info = zipfile.ZipInfo.from_file(p, os.path.relpath(p, DIST))
                if f.endswith(".sh"):
                    info.external_attr = (0o755 << 16)
                with open(p, "rb") as fh:
                    z.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(os.path.join(DIST, "EASYROMS")) for f in fs)
    print("dist ready: %.1f MB, zip %.1f MB" % (total / 1e6, os.path.getsize(zpath) / 1e6))


if __name__ == "__main__":
    main()
