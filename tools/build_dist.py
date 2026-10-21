"""Assemble dist/ for the SD card:  dist/EASYROMS/ports/...  and  dist/BOOT/...

The app comes from device/<app>/ where <app> is set in appliance.json; the
launchers and helper scripts are rendered from device/system/*.in.
Also writes dist/<title>-beta.zip. Scripts get Unix (LF) line endings.
"""
import datetime
import json
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import appliance  # noqa: E402

DEV = os.path.join(ROOT, "device")
SYS = os.path.join(DEV, "system")
DIST = os.path.join(ROOT, "dist")
PORTS = os.path.join(DIST, "EASYROMS", "ports")

SKIP_DIRS = {"__pycache__", "save", "shots", "test"}
SKIP_FILES = {"crash.log", "log.txt", "boot_log.txt", "build.ps1"}  # build.ps1 = PC-side build hook
LF_EXT = (".sh", ".py", ".txt", ".pgn", ".json", ".conf")


def copy_tree(src, dst):
    for base, dirs, files in os.walk(src):
        rel = os.path.relpath(base, src)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not (rel == "puzzles" and d == "daily")
                   and not (rel == "bin" and d == "windows")]  # PC test binaries stay on the PC
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


def main():
    cfg = appliance.load()
    app, title = cfg["app"], cfg["title"]
    src = os.path.join(DEV, app)
    if not os.path.isfile(os.path.join(src, "main.py")) and not os.path.isfile(os.path.join(src, "start")):
        raise SystemExit("device/%s/ needs a main.py (Python) or an executable 'start' (native app)" % app)
    if os.path.isdir(os.path.join(DIST, "EASYROMS")):
        shutil.rmtree(os.path.join(DIST, "EASYROMS"))
    os.makedirs(PORTS, exist_ok=True)
    out = os.path.join(PORTS, app)
    copy_tree(src, out)
    # build date: the app treats any clock earlier than this as wrong (no RTC on the R36S)
    os.makedirs(os.path.join(out, "data"), exist_ok=True)
    with open(os.path.join(out, "data", "build.json"), "w") as f:
        json.dump({"date": datetime.date.today().isoformat(), "app": app, "title": title}, f)
    if os.path.isdir(os.path.join(out, "puzzles")):
        os.makedirs(os.path.join(out, "puzzles", "daily"), exist_ok=True)
    # launchers for the "ports" install + their boot-mode helpers
    appliance.render_file(os.path.join(SYS, "port.sh.in"), os.path.join(PORTS, title + ".sh"), cfg)
    appliance.render_file(os.path.join(SYS, "port-bootmode.sh.in"), os.path.join(PORTS, title + " Boot Mode.sh"), cfg)
    for name in ("autoboot.sh", "boot_run.sh"):
        appliance.render_file(os.path.join(SYS, name + ".in"), os.path.join(out, "tools", name), cfg)
    appliance.render_file(os.path.join(DEV, "README.txt"), os.path.join(DIST, "README.txt"), cfg)
    zpath = os.path.join(DIST, "%s-beta.zip" % title)
    for old in os.listdir(DIST):
        if old.endswith("-beta.zip") and old != os.path.basename(zpath):
            os.remove(os.path.join(DIST, old))
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(DIST):
            for f in files:
                p = os.path.join(base, f)
                if p == zpath or f.endswith("-beta.zip"):
                    continue
                info = zipfile.ZipInfo.from_file(p, os.path.relpath(p, DIST))
                if f.endswith(".sh") or f == "start":
                    info.external_attr = (0o755 << 16)
                with open(p, "rb") as fh:
                    z.writestr(info, fh.read(), zipfile.ZIP_DEFLATED)
    total = sum(os.path.getsize(os.path.join(b, f)) for b, _, fs in os.walk(os.path.join(DIST, "EASYROMS")) for f in fs)
    print("dist ready for %s (%s): %.1f MB, zip %.1f MB" % (title, app, total / 1e6, os.path.getsize(zpath) / 1e6))


if __name__ == "__main__":
    main()
