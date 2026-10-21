#!/bin/bash
# ChessOS boot mode (EXPERIMENTAL)
# Runs ChessOS before EmulationStation starts, using a systemd drop-in.
# Nothing in ArkOS itself is edited; "disable" removes the drop-in again.
#
# usage: sudo bash autoboot.sh enable | disable | status

GAMEDIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
UNIT="emulationstation.service"
DROPDIR="/etc/systemd/system/$UNIT.d"
DROP="$DROPDIR/10-chessos.conf"

have_unit() {
  systemctl cat "$UNIT" > /dev/null 2>&1
}

case "$1" in
  enable)
    if ! have_unit; then
      echo "Could not find $UNIT on this system."
      echo "Boot mode is not supported on this ArkOS build. Nothing was changed."
      exit 2
    fi
    mkdir -p "$DROPDIR"
    cat > "$DROP" <<EOF
# Added by ChessOS (remove this file to undo)
[Service]
TimeoutStartSec=infinity
ExecStartPre=-/bin/bash "$GAMEDIR/tools/boot_run.sh"
EOF
    systemctl daemon-reload
    echo "ChessOS boot mode: ON"
    echo "ChessOS will start every time the R36S boots."
    echo "Run 'ChessOS Boot Mode' again to turn it off."
    ;;
  disable)
    rm -f "$DROP"
    rmdir "$DROPDIR" 2> /dev/null
    systemctl daemon-reload
    echo "ChessOS boot mode: OFF"
    echo "Your R36S will boot straight into EmulationStation again."
    ;;
  status)
    if [ -f "$DROP" ]; then echo "enabled"; else echo "disabled"; fi
    ;;
  *)
    echo "usage: $0 enable | disable | status"
    exit 1
    ;;
esac
