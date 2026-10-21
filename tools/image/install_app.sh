#!/bin/bash
# Install/refresh the appliance app (/opt/<app> + boot session + systemd drop-in)
# inside an ArkOS root filesystem image file using debugfs (no root, no mounting).
# The app name comes from appliance.json.
#   install_app.sh ROOT_EXT4 REPO_DIR
# Used by build_image.sh (fresh image) and card_update.ps1 (existing card).
set -e
ROOTFS=${1:?root.ext4}
REPO=${2:?repo}
D=/usr/sbin/debugfs
ARK=1002
TMP=$(mktemp -d)
CMD=$TMP/install.debugfs
CFG() { python3 "$REPO/tools/appliance.py" get "$1"; }
APP=$(CFG app)
TITLE=$(CFG title)
APP_SRC=$REPO/dist/EASYROMS/ports/$APP
SYS=$REPO/device/system
DROPDIR=/etc/systemd/system/emulationstation.service.d
DROP=10-$APP.conf

[ -f "$APP_SRC/main.py" ] || [ -f "$APP_SRC/start" ] || { echo "dist/ has no $APP: run setup.ps1 build"; exit 1; }
echo "  app: $TITLE -> /opt/$APP"

# A card that lost power has an unreplayed journal and small errors; debugfs
# doesn't replay journals, so repair first (this works on a copy, never the card).
/usr/sbin/e2fsck -fy "$ROOTFS" > "$TMP/repair.log" 2>&1 || true
if grep -qiE "MODIFIED|recovering journal|Fix\? yes" "$TMP/repair.log"; then
  echo "  repaired filesystem first (unclean shutdown): $(grep -ciE 'Fix\? yes' "$TMP/repair.log") fix(es)"
fi

own() { printf 'sif "%s" uid %s\nsif "%s" gid %s\n' "$1" $ARK "$1" $ARK >> "$CMD"; }
isdir() { $D -R "stat \"$1\"" "$ROOTFS" 2>/dev/null | grep -q "Type: directory"; }
# debugfs "mkdir" on an existing directory leaves an orphaned inode, so only
# create directories that are missing
mkd() { isdir "$1" || echo "mkdir \"$1\"" >> "$CMD"; own "$1"; }

: > "$CMD"
mkd "/opt/$APP"
(cd "$APP_SRC" && find . -mindepth 1 -type d -not -name __pycache__ | sort) | while read -r d; do
  mkd "/opt/$APP/${d#./}"
done
(cd "$APP_SRC" && find . -type f -not -path "*/__pycache__/*" | sort) | while read -r f; do
  p="/opt/$APP/${f#./}"
  printf 'rm "%s"\nwrite "%s" "%s"\n' "$p" "$APP_SRC/${f#./}" "$p" >> "$CMD"; own "$p"
  case "$f" in *.sh|./start) echo "sif \"$p\" mode 0100755" >> "$CMD" ;; esac
done

python3 "$REPO/tools/appliance.py" render "$SYS/boot.sh.in" "$TMP/boot.sh"
python3 "$REPO/tools/appliance.py" render "$SYS/dropin.conf.in" "$TMP/$DROP"
cat >> "$CMD" <<EOF
rm /opt/$APP/boot.sh
write "$TMP/boot.sh" /opt/$APP/boot.sh
sif /opt/$APP/boot.sh mode 0100755
EOF
own "/opt/$APP/boot.sh"

# systemd drop-in: ours in, any other appliance's out (switching apps on a card)
isdir "$DROPDIR" || echo "mkdir $DROPDIR" >> "$CMD"
for f in $($D -R "ls $DROPDIR" "$ROOTFS" 2>/dev/null | tr ' ' '\n' | grep -E '^10-.*\.conf$' || true); do
  [ "$f" = "$DROP" ] && continue
  if $D -R "cat $DROPDIR/$f" "$ROOTFS" 2>/dev/null | grep -q "^ExecStart=/opt/"; then
    echo "  removing the previous app's boot entry: $f"
    echo "rm $DROPDIR/$f" >> "$CMD"
  fi
done
cat >> "$CMD" <<EOF
rm $DROPDIR/$DROP
write "$TMP/$DROP" $DROPDIR/$DROP
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
