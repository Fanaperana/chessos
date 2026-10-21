#!/bin/bash
# Started by systemd (boot mode) right before EmulationStation.
GAMEDIR="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$GAMEDIR" || exit 0
export CHESSOS_DEVICE=1
export HOME="${HOME:-/home/ark}"
export SDL_GAMECONTROLLERCONFIG_FILE="$GAMEDIR/assets/gamecontrollerdb.txt"
python3 main.py > "$GAMEDIR/boot_log.txt" 2>&1
exit 0
