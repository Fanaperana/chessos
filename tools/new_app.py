"""Create a new appliance app from a template and make it the active app.

  python tools/new_app.py NAME "Title" [--env PREFIX] [--tagline TEXT] [--template python-sdl|native]
  python tools/new_app.py --use NAME          # switch appliance.json to an existing app

python-sdl  copies the shared ChessOS framework (graphics, input, motion, audio,
            UI, scene stack, save data) + a "hello" starter screen.
native      an empty app folder with a 'start' script: put your aarch64 binary in
            bin/ (needs glibc <= 2.30) and launch it from 'start'.
Each app keeps its own settings in device/<name>/app.json; appliance.json
(the single setting the build reads) is a copy of the active app's.
"""
import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import appliance  # noqa: E402

FRAMEWORK_SRC = os.path.join(ROOT, "device", "chessos")
FRAMEWORK_FILES = [
    "lib", "app/__init__.py", "app/core.py", "app/gfx.py", "app/inputs.py", "app/motion.py", "app/audio.py",
    "app/ui.py", "app/progress.py", "app/scenes/__init__.py", "app/scenes/dialog.py",
    "assets/fonts", "assets/gamecontrollerdb.txt", "assets/sfx", "assets/sprites/circle.spr",
]

NATIVE_START = """#!/bin/bash
# @TITLE@ launcher, run by boot.sh (or the port launcher) from this folder.
# Exit with 10 = power off, 11 = restart, 0 = ArkOS menus.
cd "$(dirname "$(readlink -f "$0")")"
exec ./bin/@APP@ "$@"
"""


def use(name):
    meta = os.path.join(ROOT, "device", name, "app.json")
    if not os.path.exists(meta):
        raise SystemExit("device/%s/app.json not found" % name)
    with open(meta, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["app"] = name
    with open(os.path.join(ROOT, "appliance.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    appliance.load()  # validates
    print("active app: %s (%s)" % (cfg["title"], name))


def create(a):
    dst = os.path.join(ROOT, "device", a.name)
    if os.path.exists(dst):
        raise SystemExit("device/%s already exists" % a.name)
    cfg = {"app": a.name, "title": a.title, "env": a.env or a.name.upper().replace("-", "_"),
           "tagline": a.tagline or ""}
    appliance.load  # noqa: B018  (validated below via use())
    os.makedirs(dst)
    if a.template == "python-sdl":
        for rel in FRAMEWORK_FILES:
            s, d = os.path.join(FRAMEWORK_SRC, rel), os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if not os.path.exists(s):
                if rel.endswith("__init__.py"):
                    open(d, "w").close()
                continue
            if os.path.isdir(s):
                shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                shutil.copyfile(s, d)
        tdir = os.path.join(ROOT, "templates", "python-sdl")
        for base, _, files in os.walk(tdir):
            for f in files:
                rel = os.path.relpath(os.path.join(base, f), tdir)
                appliance.render_file(os.path.join(base, f), os.path.join(dst, rel), cfg)
    else:
        os.makedirs(os.path.join(dst, "bin"))
        with open(os.path.join(dst, "start"), "w", newline="\n") as f:
            f.write(appliance.render(NATIVE_START, cfg))
        with open(os.path.join(dst, "assets_README.txt"), "w") as f:
            f.write("Put your aarch64 binary in bin/%s (glibc <= 2.30). Optional: assets/bootlogo.png, "
                    "assets/gamecontrollerdb.txt.\n" % a.name)
    with open(os.path.join(dst, "app.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump({k: v for k, v in cfg.items() if k != "app"}, f, indent=2)
        f.write("\n")
    print("created device/%s from the %s template" % (a.name, a.template))
    use(a.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("title", nargs="?")
    ap.add_argument("--env")
    ap.add_argument("--tagline")
    ap.add_argument("--template", default="python-sdl", choices=["python-sdl", "native"])
    ap.add_argument("--use", metavar="NAME")
    a = ap.parse_args()
    if a.use:
        use(a.use)
    elif a.name and a.title:
        create(a)
    else:
        ap.print_help()
