"""Edit the ArkOS BOOT (FAT) partition image for ChessOS.

- Install the ChessOS boot logo (the ArkOS one is kept as logo_arkos.bmp)
- Optional --panel N: switch to ScreenFiles/Panel N/ (default: keep the
  release's own screen file, which is the one that works on the K36 we tested)

FAT is case-insensitive for the bootloader but pyfatfs is not, so existing
names (often 8.3 upper case, e.g. EXTLINUX/EXTLINUX.CONF) are looked up.
usage: edit_boot.py boot.fat DIST_BOOT_DIR [--panel N]
"""
import argparse

from pyfatfs.PyFatFS import PyFatFS


def find(fs, path):
    """Resolve a path case-insensitively; returns the real path or None."""
    cur = ""
    for part in [p for p in path.split("/") if p]:
        names = fs.listdir(cur or "/")
        match = [n for n in names if n.lower() == part.lower()]
        if not match:
            return None
        cur += "/" + match[0]
    return cur or "/"


def put(fs, path, data):
    """Delete-then-write (pyfatfs breaks when overwriting with smaller data)."""
    if fs.exists(path):
        fs.remove(path)
    fs.writebytes(path, data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("logo_dir")
    ap.add_argument("--panel", type=int)
    a = ap.parse_args()
    fs = PyFatFS(a.image)
    try:
        conf_path = find(fs, "/extlinux/extlinux.conf")
        if a.panel:
            pdir = find(fs, "/ScreenFiles/Panel %d" % a.panel)
            if not pdir:
                raise SystemExit("no ScreenFiles/Panel %d in this image" % a.panel)
            dtb = [n for n in fs.listdir(pdir) if n.lower().endswith(".dtb")][0]
            put(fs, find(fs, "/" + dtb) or "/" + dtb, fs.readbytes(pdir + "/" + dtb))
            conf = fs.readbytes(conf_path).decode("utf-8")
            lines = [("  FDT /" + dtb) if l.strip().startswith("FDT ") else l for l in conf.splitlines()]
            put(fs, conf_path, ("\n".join(lines) + "\n").encode("utf-8"))

        logo_path = find(fs, "/logo.bmp") or "/logo.bmp"
        if fs.exists(logo_path) and not find(fs, "/logo_arkos.bmp"):
            put(fs, "/logo_arkos.bmp", fs.readbytes(logo_path))
        with open(a.logo_dir + "/logo.bmp", "rb") as f:
            logo = f.read()
        put(fs, logo_path, logo)
        put(fs, find(fs, "/logo_kernel.bmp") or "/logo_kernel.bmp", logo)

        print(fs.readbytes(conf_path).decode("utf-8").strip())
    finally:
        fs.close()


if __name__ == "__main__":
    main()
