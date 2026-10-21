# Third-party material

ChessOS's own code is MIT-licensed (see `LICENSE`). It bundles or uses:

| What | Where | Licence |
|---|---|---|
| Lichess puzzle database | `device/chessos/data/puzzles/*.pgn` (converted) | CC0 1.0 - [database.lichess.org](https://database.lichess.org/#puzzles) |
| Nunito font | `device/chessos/assets/fonts/Nunito-*.ttf` | SIL Open Font License 1.1 (`LICENSE-nunito.txt`) |
| DejaVu Sans font (also used to draw the chess pieces and icons) | `device/chessos/assets/fonts/DejaVuSans.ttf` | Bitstream Vera / DejaVu licence (`LICENSE-dejavu.txt`) |
| PySDL2 | `device/chessos/lib/sdl2/` (the copy PortMaster ships) | Public domain (CC0) or zlib |
| SDL_GameControllerDB | `device/chessos/assets/gamecontrollerdb.txt` | zlib |
| ArkOS-K36 (base system of the SD card image) | downloaded at build time, not stored here | see [AeolusUX/ArkOS-K36](https://github.com/AeolusUX/ArkOS-K36) |
| motion.dev | design reference only; `app/motion.py` is an independent Python re-implementation of its spring/easing model | - |

Voice clips are generated on your own PC with the Windows speech voice by
`setup.ps1 build` and are not included in this repository.
