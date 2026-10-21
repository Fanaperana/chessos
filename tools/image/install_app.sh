#!/bin/bash
# Install/refresh ChessOS (/opt/chessos + boot session + systemd drop-in) inside
# an ArkOS root filesystem image file using debugfs (no root, no mounting).
#   install_app.sh ROOT_EXT4 REPO_DIR
# Used by build_image.sh (fresh image) and update_card (existing card).
set -e
ROOTFS=${1:?root.ext4}
REPO=${2:?repo}
APP_SRC=$REPO/dist/EASYROMS/ports/chessos
SYS=$REPO/device/system
D=/usr/sbin/debugfs
ARK=1002
TMP=$(mktemp -d)
CMD=$TMP/install.debugfs

[ -f "$APP_SRC/main.py" ] || { echo "dist/ missing: run setup.ps1 build"; exit 1; }
own() { printf 'sif "%s" uid %s\nsif "%s" gid %s\n' "$1" $ARK "$1" $ARK >> "$CMD"; }
# debugfs "mkdir" on an existing directory leaves an orphaned inode, so only
# create directories that are missing
mkd() {
  if ! $D -R "stat \"$1\"" "$ROOTFS" 2>/dev/null | grep -q "Type: directory"; then
    echo "mkdir \"$1\"" >> "$CMD"
  fi
  own "$1"
}

: > "$CMD"
mkd /opt/chessos
(cd "$APP_SRC" && find . -mindepth 1 -type d -not -name __pycache__ | sort) | while read -r d; do
  mkd "/opt/chessos/${d#./}"
done
(cd "$APP_SRC" && find . -type f -not -path "*/__pycache__/*" | sort) | while read -r f; do
  p="/opt/chessos/${f#./}"
  printf 'rm "%s"\nwrite "%s" "%s"\n' "$p" "$APP_SRC/${f#./}" "$p" >> "$CMD"; own "$p"
  case "$f" in *.sh) echo "sif \"$p\" mode 0100755" >> "$CMD" ;; esac
done
tr -d '\r' < "$SYS/boot.sh" > "$TMP/boot.sh"
tr -d '\r' < "$SYS/10-chessos.conf" > "$TMP/10-chessos.conf"
cat >> "$CMD" <<EOF
rm /opt/chessos/boot.sh
write "$TMP/boot.sh" /opt/chessos/boot.sh
sif /opt/chessos/boot.sh mode 0100755
EOF
own /opt/chessos/boot.sh
if ! $D -R "stat /etc/systemd/system/emulationstation.service.d" "$ROOTFS" 2>/dev/null | grep -q "Type: directory"; then
  echo "mkdir /etc/systemd/system/emulationstation.service.d" >> "$CMD"
fi
cat >> "$CMD" <<EOF
rm /etc/systemd/system/emulationstation.service.d/10-chessos.conf
write "$TMP/10-chessos.conf" /etc/systemd/system/emulationstation.service.d/10-chessos.conf
EOF
echo "  $(grep -c '^write' "$CMD") files"

$D -w -f "$CMD" "$ROOTFS" > "$TMP/debugfs.log" 2>&1
# "rm" of a file that isn't there yet and "mkdir" of an existing dir are expected
if grep -v '^debugfs' "$TMP/debugfs.log" | grep -viE 'File not found by ext2_lookup|already exists|^Allocated inode' \
    | grep -qiE 'error|could not|failed|not found'; then
  grep -v '^debugfs' "$TMP/debugfs.log" | grep -viE 'File not found by ext2_lookup|already exists|^Allocated inode' | head -20
  exit 1
fi
/usr/sbin/e2fsck -fn "$ROOTFS" > "$TMP/e2fsck.log" 2>&1 || { tail -20 "$TMP/e2fsck.log"; exit 1; }
echo "  filesystem check: $(tail -1 "$TMP/e2fsck.log")"
rm -rf "$TMP"
