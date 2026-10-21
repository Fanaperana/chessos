#!/bin/bash
# Build the ChessOS SD card image from the ArkOS-K36 image. Runs in WSL/Linux, no root needed.
#
#   build_image.sh WORK_DIR REPO_DIR
#
#   WORK_DIR/arkos.img          decompressed ArkOS_K36 image (setup.ps1 image downloads it)
#   REPO_DIR/dist/...           output of tools/build_dist.py
#   -> WORK_DIR/chessos.img
#
# Env: PANEL=N   use ScreenFiles/Panel N instead of the release's default screen file
set -e
WORK=${1:?work dir}
REPO=${2:?repo dir}
DIST=$REPO/dist
APP_SRC=$DIST/EASYROMS/ports/chessos
SYS=$REPO/device/system
D=/usr/sbin/debugfs
PY=${PY:-$HOME/cosvenv/bin/python}
ROOT_OFF_MB=516      # partition 2 starts at 541065216 bytes
ARK_UID=1002

[ -x "$D" ] || { echo "debugfs missing: sudo apt install e2fsprogs"; exit 1; }
if [ ! -x "$PY" ]; then
  echo "creating helper venv ($PY)"
  python3 -m venv "$(dirname "$(dirname "$PY")")"
  "$(dirname "$PY")/pip" install -q pyfatfs
fi

cd "$WORK"
echo "[1/7] fresh copy of the ArkOS image"
cp arkos.img chessos.img
rm -f root.ext4
dd if=chessos.img of=root.ext4 bs=1M skip=$ROOT_OFF_MB count=8192 status=none

echo "[2/7] install script for /opt/chessos"
CMD=$WORK/install.debugfs
: > "$CMD"
cd "$APP_SRC"
{
  echo "mkdir /opt/chessos"
  echo "sif /opt/chessos uid $ARK_UID"
  echo "sif /opt/chessos gid $ARK_UID"
} >> "$CMD"
find . -mindepth 1 -type d -not -name __pycache__ | sort | while read -r d; do
  p="/opt/chessos/${d#./}"
  printf 'mkdir "%s"\nsif "%s" uid %s\nsif "%s" gid %s\n' "$p" "$p" $ARK_UID "$p" $ARK_UID >> "$CMD"
done
find . -type f -not -path "*/__pycache__/*" | sort | while read -r f; do
  p="/opt/chessos/${f#./}"
  printf 'write "%s" "%s"\nsif "%s" uid %s\nsif "%s" gid %s\n' "$APP_SRC/${f#./}" "$p" "$p" $ARK_UID "$p" $ARK_UID >> "$CMD"
  case "$f" in *.sh) echo "sif \"$p\" mode 0100755" >> "$CMD" ;; esac
done
cd "$WORK"
tr -d '\r' < "$SYS/boot.sh" > boot.sh
tr -d '\r' < "$SYS/10-chessos.conf" > 10-chessos.conf
# ArkOS moves /home/ark/fstab to /etc/fstab on first boot: make the EASYROMS
# mounts optional so a failed format can never freeze the boot
$D -R "cat /home/ark/fstab" root.ext4 2>/dev/null > fstab.orig
sed -e '/\/roms exfat/ s/noatime/noatime,nofail,x-systemd.device-timeout=10s/' \
    -e '/\/opt\/system\/Tools none bind/ s/bind/bind,nofail/' \
    -e '/\/boot vfat/ s/defaults/defaults,nofail/' fstab.orig > fstab.new
cat >> "$CMD" <<EOF
write "$WORK/boot.sh" /opt/chessos/boot.sh
sif /opt/chessos/boot.sh mode 0100755
sif /opt/chessos/boot.sh uid $ARK_UID
sif /opt/chessos/boot.sh gid $ARK_UID
mkdir /etc/systemd/system/emulationstation.service.d
write "$WORK/10-chessos.conf" /etc/systemd/system/emulationstation.service.d/10-chessos.conf
rm /home/ark/fstab
write "$WORK/fstab.new" /home/ark/fstab
sif /home/ark/fstab mode 0100644
EOF
echo "    $(grep -c '^write' "$CMD") files"

echo "[3/7] writing into the ext4 root filesystem"
$D -w -f "$CMD" root.ext4 > debugfs.log 2>&1
if grep -v '^debugfs' debugfs.log | grep -qiE 'error|could not|failed|not found'; then
  grep -v '^debugfs' debugfs.log | head -20
  exit 1
fi

echo "[4/7] checking the filesystem"
/usr/sbin/e2fsck -fn root.ext4 > e2fsck.log 2>&1 || { tail -20 e2fsck.log; exit 1; }
tail -1 e2fsck.log
echo "    first-boot fstab:"
$D -R "cat /home/ark/fstab" root.ext4 2>/dev/null | sed 's/^/      /'

echo "[5/7] putting the root filesystem back into the image"
dd if=root.ext4 of=chessos.img bs=1M seek=$ROOT_OFF_MB conv=notrunc status=none

echo "[6/7] BOOT partition: ChessOS logo${PANEL:+ + screen Panel $PANEL}"
dd if=chessos.img of="$HOME/boot.fat" bs=1M skip=16 count=500 status=none
"$PY" "$REPO/tools/image/edit_boot.py" "$HOME/boot.fat" "$DIST/BOOT" ${PANEL:+--panel $PANEL}
/sbin/fsck.vfat -n "$HOME/boot.fat" | tail -1
dd if="$HOME/boot.fat" of=chessos.img bs=1M seek=16 conv=notrunc status=none

echo "[7/7] done"
ls -la chessos.img
echo "DONE"
