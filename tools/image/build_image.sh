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
D=/usr/sbin/debugfs
PY=${PY:-$HOME/cosvenv/bin/python}
ROOT_OFF_MB=516      # partition 2 starts at 541065216 bytes

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

echo "[2/7] ChessOS -> /opt/chessos (boots instead of EmulationStation)"
bash "$REPO/tools/image/install_app.sh" "$WORK/root.ext4" "$REPO"

echo "[3/7] first-boot fstab: EASYROMS mounts optional (a failed format can't freeze boot)"
# ArkOS moves /home/ark/fstab to /etc/fstab on first boot
$D -R "cat /home/ark/fstab" root.ext4 2>/dev/null > fstab.orig
sed -e '/\/roms exfat/ s/noatime/noatime,nofail,x-systemd.device-timeout=10s/' \
    -e '/\/opt\/system\/Tools none bind/ s/bind/bind,nofail/' \
    -e '/\/boot vfat/ s/defaults/defaults,nofail/' fstab.orig > fstab.new
cat > fstab.debugfs <<EOF
rm /home/ark/fstab
write $WORK/fstab.new /home/ark/fstab
sif /home/ark/fstab mode 0100644
EOF
$D -w -f fstab.debugfs root.ext4 > /dev/null 2>&1
$D -R "cat /home/ark/fstab" root.ext4 2>/dev/null | sed 's/^/      /'

echo "[4/7] checking the filesystem"
/usr/sbin/e2fsck -fn root.ext4 > e2fsck.log 2>&1 || { tail -20 e2fsck.log; exit 1; }
tail -1 e2fsck.log

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
