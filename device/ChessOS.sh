#!/bin/bash
# ChessOS - learn chess, one day at a time.
# ArkOS port launcher: copy this file and the "chessos" folder into /roms/ports/

GAMEDIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)/chessos"
CUR_TTY=/dev/tty0

sudo chmod 666 $CUR_TTY 2>/dev/null
printf "\033c" > $CUR_TTY 2>/dev/null
echo "Starting ChessOS..." > $CUR_TTY 2>/dev/null

cd "$GAMEDIR" || exit 1

PY="$(command -v python3)"
if [ -z "$PY" ]; then
  echo "ChessOS needs python3, which was not found." > $CUR_TTY
  sleep 5
  exit 1
fi

export CHESSOS_DEVICE=1
export SDL_GAMECONTROLLERCONFIG_FILE="$GAMEDIR/assets/gamecontrollerdb.txt"

"$PY" main.py > "$GAMEDIR/log.txt" 2>&1

printf "\033c" > $CUR_TTY 2>/dev/null
