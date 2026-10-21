#!/bin/bash
# ChessOS session (replaces EmulationStation as the boot program).
# Exit codes from ChessOS: 10 = power off, 11 = restart, anything else = open
# the ArkOS menus (EmulationStation). Leaving EmulationStation returns here.
# A copy of the log goes to EASYROMS (/roms/chessos_log.txt) so it can be read
# on a PC. Nothing is ever written to the BOOT partition: a power cut while it
# is being written could stop the handheld from booting.

APP=/opt/chessos
ES=/usr/bin/emulationstation/emulationstation.sh
LOG="$APP/log.txt"
PCLOG=/roms/chessos_log.txt

sudo chmod 666 /dev/tty1 2>/dev/null
export TERM=linux
export XDG_RUNTIME_DIR=/run/user/$UID/
export CHESSOS_DEVICE=1
export CHESSOS_FRONTEND=1
export SDL_GAMECONTROLLERCONFIG_FILE="$APP/assets/gamecontrollerdb.txt"

say() { printf "%s\n" "$*" > /dev/tty1; }
copylog() { mountpoint -q /roms && cp "$LOG" "$PCLOG" 2>/dev/null && sync; }

# EASYROMS: ArkOS's first-boot format can fail on some cards. If partition 3
# exists but has NO filesystem at all, format it once and restore the default
# folders. A partition with any filesystem is never touched.
P3=/dev/mmcblk1p3
if [ -b "$P3" ] && ! mountpoint -q /roms && [ -z "$(sudo blkid -o value -s TYPE "$P3" 2>/dev/null)" ]; then
  say "   Preparing EASYROMS (one time, about a minute)..."
  if sudo mkfs.exfat -n EASYROMS "$P3" > /dev/null 2>&1; then
    sudo mount "$P3" /roms 2>/dev/null && [ -d /.rm_roms ] && sudo cp -r /.rm_roms/. /roms/ 2>/dev/null
    sync
  fi
fi
if ! mountpoint -q /roms && [ -b "$P3" ]; then
  sudo mount "$P3" /roms 2>/dev/null
fi

while true; do
  printf "\033c" > /dev/tty1
  say ""
  say "   ChessOS is starting..."
  {
    echo "=== ChessOS start $(date) uid=$(id -u) python=$(python3 --version 2>&1)"
    cd "$APP"
    python3 -u main.py
    echo "=== exit code $?"
  } > "$LOG" 2>&1 &
  pid=$!
  # one early copy, so a start-up hang can still be diagnosed on a PC
  for _ in $(seq 30); do kill -0 $pid 2>/dev/null || break; sleep 1; done
  kill -0 $pid 2>/dev/null && copylog
  wait $pid
  code=$(tail -1 "$LOG" | sed -n 's/^=== exit code //p')
  code=${code:-1}
  copylog
  case "$code" in
    10) sync; sudo systemctl poweroff; exit 0 ;;
    11) sync; sudo systemctl reboot; exit 0 ;;
    0)  "$ES" ;;   # Wi-Fi, updates, games... then back to ChessOS
    *)  say "   ChessOS stopped (code $code). Opening ArkOS menus..."; sleep 2; "$ES" ;;
  esac
done
