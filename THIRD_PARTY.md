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
| Stockfish 9 (device) / Stockfish 19 (PC testing) | downloaded by `tools/fetch_engines.py` into `device/chessos/bin/`, not stored here | GPL-3.0 - source: [official-stockfish/Stockfish](https://github.com/official-stockfish/Stockfish), Ubuntu package `stockfish 9-2` |
| Piper TTS 2023.11.14-2 | downloaded into `device/chessos/bin/` | MIT - [rhasspy/piper](https://github.com/rhasspy/piper) |
| Piper voice `en_US-lessac-low` | downloaded into `device/chessos/assets/piper/` | trained on the Lessac / Blizzard 2013 dataset - non-commercial research licence, so it is downloaded for your own device and never committed |
| Kokoro-82M voice clips | `device/chessos/assets/voice/*.wav` | Apache-2.0 - [hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) |
| motion.dev | design reference only; `app/motion.py` is an independent Python re-implementation of its spring/easing model | - |

An SD card built with `setup.ps1 image` contains the Stockfish binary (GPL-3.0);
its source is available from the links above.
