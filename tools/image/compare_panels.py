"""Compare the panel settings in the ArkOS-K36 screen files (device trees).

usage: compare_panels.py <folder with the extracted BOOT partition>
needs: pip install fdt
Prints resolution, refresh rate and init-sequence hash for every screen file,
which helps pick the right Panel when a screen stays black.
"""
import glob
import hashlib
import os
import sys

import fdt

if len(sys.argv) < 2:
    raise SystemExit(__doc__)
BASE = sys.argv[1]


def prop(node, name):
    p = node.get_property(name)
    return None if p is None else (list(p.data) if hasattr(p, "data") else p.value)


def panel_info(path):
    with open(path, "rb") as f:
        raw = f.read()
    tree = fdt.parse_dtb(raw)
    out = {"md5": hashlib.md5(raw).hexdigest()[:8], "size": len(raw)}
    for node_path in ("/dsi@ff450000/panel@0/display-timings/timing0",):
        try:
            t = tree.get_node(node_path)
        except Exception:
            continue
        g = lambda n: (prop(t, n) or [0])[0]
        clk = g("clock-frequency")
        ht = g("hactive") + g("hfront-porch") + g("hback-porch") + g("hsync-len")
        vt = g("vactive") + g("vfront-porch") + g("vback-porch") + g("vsync-len")
        out["mode"] = "%dx%d" % (g("hactive"), g("vactive"))
        out["hz"] = round(clk / float(ht * vt), 2) if ht and vt else 0
        out["clk"] = clk
        out["porch"] = (g("hfront-porch"), g("hback-porch"), g("hsync-len"), g("vfront-porch"), g("vback-porch"), g("vsync-len"))
    try:
        p = tree.get_node("/dsi@ff450000/panel@0")
        init = p.get_property("panel-init-sequence")
        data = bytes(init.data) if init is not None else b""
        out["init"] = hashlib.md5(data).hexdigest()[:8] + " (%d bytes)" % len(data)
        out["compatible"] = prop(p, "compatible")
    except Exception as e:
        out["init"] = "?" + str(e)
    return out


files = [os.path.join(BASE, "rf3536k4ka.dtb")] + sorted(glob.glob(os.path.join(BASE, "ScreenFiles", "Panel *", "*.dtb")))
for f in files:
    label = os.path.relpath(f, BASE)
    print(label, panel_info(f))
