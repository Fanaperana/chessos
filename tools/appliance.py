"""The one setting that names the app the handheld boots into: appliance.json.

  app      folder under device/, installed to /opt/<app>   (a-z, 0-9, - and _)
  title    display name (boot messages, logo, port launcher)
  env      prefix of the environment variables passed to the app (<ENV>_DEVICE ...)
  tagline  line under the title on the boot logo

Used from Python (load()) and from shell / PowerShell:
  python3 tools/appliance.py get app
  python3 tools/appliance.py render device/system/boot.sh.in out/boot.sh
Templates use @APP@ @TITLE@ @ENV@ @TAGLINE@.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT = {"app": "chessos", "title": "ChessOS", "env": "CHESSOS", "tagline": ""}


def load(path=None):
    path = path or os.environ.get("APPLIANCE_CONFIG") or os.path.join(ROOT, "appliance.json")
    cfg = dict(DEFAULT)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            cfg.update(json.load(f))
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,40}$", cfg["app"]):
        raise SystemExit("appliance.json: 'app' must be lower case letters, digits, - or _ (got %r)" % cfg["app"])
    if not re.match(r"^[A-Z][A-Z0-9_]{0,30}$", cfg["env"]):
        raise SystemExit("appliance.json: 'env' must be UPPER_CASE (got %r)" % cfg["env"])
    return cfg


def render(text, cfg=None):
    cfg = cfg or load()
    for key in ("app", "title", "env", "tagline"):
        text = text.replace("@%s@" % key.upper(), cfg[key])
    return text


def render_file(src, dst, cfg=None):
    with open(src, encoding="utf-8") as f:
        text = render(f.read().replace("\r\n", "\n"), cfg)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "get":
        print(load()[sys.argv[2]])
    elif len(sys.argv) == 4 and sys.argv[1] == "render":
        render_file(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
