#!/usr/bin/env python3
"""@TITLE@ - entry point (made from the ChessOS python-sdl template)."""
import os
import platform
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "lib"))
sys.path.insert(0, BASE)


def is_device():
    if "1" in (os.environ.get("APPLIANCE_DEVICE"), os.environ.get("@ENV@_DEVICE")):
        return True
    return sys.platform.startswith("linux") and platform.machine() in ("aarch64", "armv7l", "armv8l")


def main():
    import faulthandler
    faulthandler.enable()
    faulthandler.dump_traceback_later(20, exit=False)  # stack dump if no frame within 20 s
    from app.core import App
    from app.scenes.hello import Hello
    app = App(BASE, device=is_device())
    app.run(Hello(app))
    return app.exit_code   # 10 = power off, 11 = restart, 0 = ArkOS menus (see boot.sh)


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception:
        traceback.print_exc()
        with open(os.path.join(BASE, "crash.log"), "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
