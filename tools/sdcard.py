"""Raw SD card tool for building the ChessOS card (Windows, run as Administrator).

  read-head  DISK EXPECTED_SIZE OUT_IMG
      Copy everything before the EASYROMS partition (bootloader + BOOT + ArkOS
      rootfs) from a GPT card into OUT_IMG.
  write-head DISK EXPECTED_SIZE IMG
      Write IMG to the start of the card, then write a new GPT for this card's
      size with partition 3 (EASYROMS) stretched to the end of the card.
      The disk must be cleared and offline first (see card_write.ps1).

Safety: refuses unless the disk number is >= 3 and its size matches exactly.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import struct
import sys
import time
import zlib

SECTOR = 512
CHUNK = 4 * 1024 * 1024
IOCTL_DISK_GET_LENGTH_INFO = 0x7405C


def disk_size(path):
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wt.HANDLE
    k32.CreateFileW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE]
    k32.DeviceIoControl.restype = wt.BOOL
    k32.DeviceIoControl.argtypes = [wt.HANDLE, wt.DWORD, ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
                                    ctypes.POINTER(wt.DWORD), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [wt.HANDLE]
    GENERIC_READ = 0x80000000
    h = k32.CreateFileW(path, GENERIC_READ, 3, None, 3, 0, None)
    if not h or h == wt.HANDLE(-1).value:
        raise OSError("cannot open %s (error %d)" % (path, ctypes.get_last_error()))
    out = ctypes.c_longlong()
    ret = wt.DWORD()
    ok = k32.DeviceIoControl(h, IOCTL_DISK_GET_LENGTH_INFO, None, 0, ctypes.byref(out), 8, ctypes.byref(ret), None)
    err = ctypes.get_last_error()
    k32.CloseHandle(h)
    if not ok:
        raise OSError("size query failed (error %d)" % err)
    return out.value


def check(disk, expected):
    if disk < 3:
        raise SystemExit("refusing: disk %d is a system disk" % disk)
    path = r"\\.\PhysicalDrive%d" % disk
    size = disk_size(path)
    if size != expected:
        raise SystemExit("refusing: disk %d is %d bytes, expected %d" % (disk, size, expected))
    return path, size


def parse_gpt(lba1, entries):
    if lba1[:8] != b"EFI PART":
        raise SystemExit("no GPT found")
    f = struct.unpack("<8sIIIIQQQQ16sQIII", lba1[:92])
    hdr = dict(rev=f[1], hsize=f[2], cur=f[5], backup=f[6], first=f[7], last=f[8], guid=f[9],
               entries_lba=f[10], n=f[11], esize=f[12], ecrc=f[13])
    parts = []
    for i in range(hdr["n"]):
        e = entries[i * hdr["esize"]:(i + 1) * hdr["esize"]]
        if e[:16] == b"\0" * 16:
            continue
        first, last = struct.unpack("<QQ", e[32:48])
        name = e[56:128].decode("utf-16-le").rstrip("\0")
        parts.append(dict(index=i, first=first, last=last, name=name))
    return hdr, parts


_last = [0.0]


def progress(done, total, t0):
    """Print progress about every 5 seconds (one line each, works in logs)."""
    now = time.time()
    if now - _last[0] < 5 and done < total:
        return
    _last[0] = now
    rate = done / max(0.001, now - t0) / 1e6
    print("  %.1f / %.1f GB  (%.1f MB/s)" % (done / 1e9, total / 1e9, rate))
    sys.stdout.flush()


def read_head(disk, expected, out):
    path, size = check(disk, expected)
    with open(path, "rb", buffering=0) as d:
        head = d.read(34 * SECTOR)
        hdr, parts = parse_gpt(head[SECTOR:2 * SECTOR], head[2 * SECTOR:34 * SECTOR])
        if len(parts) != 3:
            raise SystemExit("expected 3 partitions, found %d" % len(parts))
        end = parts[2]["first"] * SECTOR
        print("partitions:", parts)
        print("copying first %.2f GB (bootloader + BOOT + rootfs)" % (end / 1e9))
        d.seek(0)
        t0, done = time.time(), 0
        with open(out, "wb") as f:
            while done < end:
                buf = d.read(min(CHUNK, end - done))
                if not buf:
                    raise SystemExit("short read at %d" % done)
                f.write(buf)
                done += len(buf)
                progress(done, end, t0)
    with open(out + ".json", "w") as f:
        json.dump({"source_size": size, "head_bytes": end, "parts": parts}, f, indent=1)
    print("\nOK ->", out)


def build_gpt(img_path, size):
    """New primary+backup GPT for a disk of `size` bytes, partition 3 to the end."""
    with open(img_path, "rb") as f:
        mbr = bytearray(f.read(SECTOR))
        lba1 = bytearray(f.read(SECTOR))
        entries = bytearray(f.read(32 * SECTOR))
    hdr, parts = parse_gpt(bytes(lba1), bytes(entries))
    n = size // SECTOR
    ent_sectors = (hdr["n"] * hdr["esize"] + SECTOR - 1) // SECTOR
    last_usable = n - 1 - ent_sectors - 1
    p3 = parts[2]
    off = p3["index"] * hdr["esize"]
    end = (last_usable + 1) // 2048 * 2048 - 1  # keep 1 MiB alignment
    struct.pack_into("<Q", entries, off + 40, end)
    ecrc = zlib.crc32(bytes(entries[:hdr["n"] * hdr["esize"]])) & 0xFFFFFFFF

    def header(cur, backup, entries_lba):
        h = bytearray(lba1[:hdr["hsize"]])
        struct.pack_into("<I", h, 16, 0)
        struct.pack_into("<QQQQ", h, 24, cur, backup, hdr["first"], last_usable)
        struct.pack_into("<Q", h, 72, entries_lba)
        struct.pack_into("<I", h, 88, ecrc)
        struct.pack_into("<I", h, 16, zlib.crc32(bytes(h)) & 0xFFFFFFFF)
        return bytes(h) + b"\0" * (SECTOR - len(h))

    primary = header(1, n - 1, 2)
    backup = header(n - 1, 1, n - 1 - ent_sectors)
    # protective MBR entry covers the whole disk
    struct.pack_into("<I", mbr, 446 + 12, min(n - 1, 0xFFFFFFFF))
    return bytes(mbr), primary, bytes(entries), backup, n, ent_sectors, (p3["first"], end)


def write_head(disk, expected, img):
    path, size = check(disk, expected)
    mbr, primary, entries, backup, n, ent_sectors, p3 = build_gpt(img, size)
    total = os.path.getsize(img)
    print("writing %.2f GB to disk %d, then GPT (EASYROMS = %.1f GB)" %
          (total / 1e9, disk, (p3[1] - p3[0] + 1) * SECTOR / 1e9))
    with open(path, "r+b", buffering=0) as d, open(img, "rb") as f:
        t0, done = time.time(), 0
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            if len(buf) % SECTOR:
                buf += b"\0" * (SECTOR - len(buf) % SECTOR)
            d.write(buf)
            done += len(buf)
            progress(done, total, t0)
        # wipe the first 1 MiB of EASYROMS so Windows sees it as new/raw
        d.seek(p3[0] * SECTOR)
        d.write(b"\0" * (1024 * 1024))
        d.seek(0)
        d.write(mbr + primary + entries)
        d.seek((n - 1 - ent_sectors) * SECTOR)
        d.write(entries + backup)
    with open(path, "rb", buffering=0) as d:
        check_hdr = d.read(2 * SECTOR)[SECTOR:]
    assert check_hdr == primary, "GPT verify failed"
    print("\nOK: card written and GPT verified")


def write_image(disk, expected, img):
    """Write a whole image (like balenaEtcher), then read it back and compare."""
    import hashlib
    path, size = check(disk, expected)
    total = os.path.getsize(img)
    if total > size:
        raise SystemExit("image is bigger than the card")
    print("writing %s (%.2f GB) to disk %d" % (img, total / 1e9, disk))
    h_src = hashlib.sha256()
    # The first 1 MiB (partition tables) is written LAST, so Windows cannot
    # mount a half-written partition and block the rest of the write.
    head_len = 1024 * 1024
    with open(path, "r+b", buffering=0) as d, open(img, "rb") as f:
        head = f.read(head_len)
        h_src.update(head)
        d.seek(head_len)
        t0, done = time.time(), head_len
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            if len(buf) % SECTOR:
                buf += b"\0" * (SECTOR - len(buf) % SECTOR)
            h_src.update(buf)
            d.write(buf)
            done += len(buf)
            progress(done, total, t0)
        d.seek(0)
        d.write(head)
    print("\nverifying...")
    h_dst = hashlib.sha256()
    with open(path, "rb", buffering=0) as d:
        t0, done = time.time(), 0
        while done < total:
            n = min(CHUNK, total - done)
            n += (SECTOR - n % SECTOR) % SECTOR
            buf = d.read(n)
            h_dst.update(buf)
            done += len(buf)
            progress(done, total, t0)
    if h_src.digest() != h_dst.digest():
        raise SystemExit("\nVERIFY FAILED: card contents differ from the image")
    print("\nOK: written and verified (sha256 %s)" % h_src.hexdigest()[:16])


def part_range(d, partnum):
    d.seek(0)
    head = d.read(34 * SECTOR)
    hdr, parts = parse_gpt(head[SECTOR:2 * SECTOR], head[2 * SECTOR:34 * SECTOR])
    p = parts[partnum - 1]
    return p["first"] * SECTOR, (p["last"] - p["first"] + 1) * SECTOR


def read_part(disk, expected, partnum, out):
    """Copy one partition (e.g. 2 = ArkOS root) into a file."""
    path, size = check(disk, expected)
    with open(path, "rb", buffering=0) as d:
        start, length = part_range(d, partnum)
        print("partition %d: offset %d, %.2f GB" % (partnum, start, length / 1e9))
        d.seek(start)
        t0, done = time.time(), 0
        with open(out, "wb") as f:
            while done < length:
                buf = d.read(min(CHUNK, length - done))
                f.write(buf)
                done += len(buf)
                progress(done, length, t0)
    with open(out + ".offset", "w") as f:
        f.write(str(start))
    print("OK ->", out)


def write_diff(disk, expected, partnum, orig, new):
    """Write back only the 4 MiB chunks of `new` that differ from `orig`."""
    path, size = check(disk, expected)
    if os.path.getsize(orig) != os.path.getsize(new):
        raise SystemExit("files differ in size")
    with open(path, "r+b", buffering=0) as d:
        start, length = part_range(d, partnum)
        if length != os.path.getsize(new):
            raise SystemExit("partition size does not match the file")
        changed = 0
        with open(orig, "rb") as a, open(new, "rb") as b:
            off = 0
            while off < length:
                x, y = a.read(CHUNK), b.read(CHUNK)
                if x != y:
                    d.seek(start + off)
                    d.write(y)
                    d.seek(start + off)
                    if d.read(len(y)) != y:
                        raise SystemExit("verify failed at offset %d" % off)
                    changed += 1
                off += len(x)
    print("OK: %d chunk(s) of 4 MiB updated and verified" % changed)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "read-part":
        read_part(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
        sys.exit(0)
    if cmd == "write-diff":
        write_diff(int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6])
        sys.exit(0)
    if cmd == "write-image":
        write_image(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
        sys.exit(0)
    if cmd == "read-head":
        read_head(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    elif cmd == "write-head":
        write_head(int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
    else:
        print(__doc__)
