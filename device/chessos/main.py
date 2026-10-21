#!/usr/bin/env python3
"""ChessOS - learn chess, one day at a time. Entry point."""
import os
import platform
import sys
import traceback

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "lib"))
sys.path.insert(0, BASE)


def is_device():
    if "1" in (os.environ.get("APPLIANCE_DEVICE"), os.environ.get("CHESSOS_DEVICE")):
        return True
    if os.environ.get("CHESSOS_DEVICE") == "0":
        return False
    return sys.platform.startswith("linux") and platform.machine() in ("aarch64", "armv7l", "armv8l")


def main():
    import faulthandler
    faulthandler.enable()
    # if no frame is drawn within 20 s, write every thread's stack to the log
    faulthandler.dump_traceback_later(20, exit=False)
    print("ChessOS: python", sys.version.split()[0], "device", is_device())
    print("ChessOS: importing app")
    from app.core import App
    print("ChessOS: app imported")
    from app.scenes.splash import Splash
    app = App(BASE, device=is_device())
    app.run(Splash(app))
    return app.exit_code


if __name__ == "__main__":
    try:
        sys.exit(main() or 0)
    except Exception:
        traceback.print_exc()
        with open(os.path.join(BASE, "crash.log"), "w") as f:
            traceback.print_exc(file=f)
        sys.exit(1)
