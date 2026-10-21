#!/bin/bash
# ChessOS Boot Mode (EXPERIMENTAL) - toggles "start ChessOS when the R36S boots".
# Run it once to turn boot mode ON, run it again to turn it OFF.
# Exiting ChessOS (Start > Exit, or Select+Start) continues into EmulationStation.

GAMEDIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)/chessos"
CUR_TTY=/dev/tty0
sudo chmod 666 $CUR_TTY 2>/dev/null
printf "\033c" > $CUR_TTY

if sudo bash "$GAMEDIR/tools/autoboot.sh" status | grep -q "enabled"; then
  sudo bash "$GAMEDIR/tools/autoboot.sh" disable > $CUR_TTY 2>&1
else
  sudo bash "$GAMEDIR/tools/autoboot.sh" enable > $CUR_TTY 2>&1
fi
sleep 4
printf "\033c" > $CUR_TTY
