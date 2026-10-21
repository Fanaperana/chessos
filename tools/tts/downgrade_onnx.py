"""Make Supertonic's ONNX models loadable by onnxruntime 1.14 (the last
release with Python 3.7 aarch64 wheels, which ArkOS needs).

The models are IR 9 / opset 19. The only operators they use whose opset-19
versions differ (Cast, Equal, Pad, Reshape, Shape) changed by adding float8 /
string types or Pad's "wrap" mode - none of which these models use - so the
graphs are relabelled IR 8 / opset 18 unchanged. This script refuses if it
finds anything that would make that unsafe.

usage: downgrade_onnx.py SRC_DIR DST_DIR
"""
import glob
import os
import sys

import onnx

SAFE_TYPES = {onnx.TensorProto.FLOAT, onnx.TensorProto.INT64, onnx.TensorProto.INT32, onnx.TensorProto.BOOL}


def check(m, name):
    for n in m.graph.node:
        if n.op_type == "Pad":
            for a in n.attribute:
                if a.name == "mode" and a.s == b"wrap":
                    raise SystemExit("%s: Pad mode 'wrap' needs opset 19" % name)
        if n.op_type in ("Cast", "CastLike"):
            for a in n.attribute:
                if a.name == "to" and a.i not in SAFE_TYPES:
                    raise SystemExit("%s: Cast to type %d" % (name, a.i))
    for t in m.graph.initializer:
        if t.data_type not in SAFE_TYPES:
            raise SystemExit("%s: initializer type %d" % (name, t.data_type))


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    for path in sorted(glob.glob(os.path.join(src, "*.onnx"))):
        name = os.path.basename(path)
        m = onnx.load(path)
        check(m, name)
        m.ir_version = 8
        for o in m.opset_import:
            if o.domain in ("", "ai.onnx") and o.version > 18:
                o.version = 18
        onnx.save(m, os.path.join(dst, name))
        print("  %s -> IR 8 / opset 18" % name)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
