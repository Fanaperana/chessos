ChessOS - learn chess, one day at a time
https://github.com/Fanaperana/chessos
========================================

These folders mirror an ArkOS SD card:

  BOOT/       -> the small FAT partition named BOOT
  EASYROMS/   -> the big partition named EASYROMS

ADD CHESSOS TO AN EXISTING ArkOS CARD (as a port)
1. Copy EASYROMS/ports/ChessOS.sh, "EASYROMS/ports/ChessOS Boot Mode.sh"
   and the EASYROMS/ports/chessos folder into the card's EASYROMS/ports/.
2. Optional boot logo: on BOOT, keep a copy of logo.bmp, then copy
   BOOT/logo.bmp (and logo_kernel.bmp) from here.
3. On the handheld: Ports > ChessOS.

For a card that boots straight into ChessOS, use `setup.ps1 image` and
`setup.ps1 flash` from the project instead (see README.md there).

CONTROLS
  D-pad / left stick  move            A  select / confirm
  B                   back / cancel   X  speak again (voice)
  Y                   hint            L1/R1  jump unit / month
  START               menu / settings SELECT stats (GitHub-style year)
  SELECT + START      quit ChessOS right away

FILES
  chessos/save/save.json     your XP, streak and crowns
  chessos/puzzles/custom/    drop your own .pgn puzzles here
  chessos/puzzles/daily/     downloaded Lichess daily puzzles (PGN)
  chessos/log.txt            log of the last run (attach it to bug reports)
