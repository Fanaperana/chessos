# Building a single-app handheld OS on ArkOS (the ChessOS recipe)

ChessOS is one app that boots straight up on an R36S-class handheld, with no
EmulationStation menu in front of it. This guide documents **how** that works
and every tweak and fix we needed, so you can build your own "*Something*OS"
with a different app on top of the same pipeline.

- Part 1 covers what is generic: hardware facts, the boot chain, building,
  flashing and updating cards.
- Part 2 covers the app framework ChessOS uses (Python + SDL2), which you can
  reuse or replace.
- Part 3 is the step-by-step checklist for **swapping ChessOS for another app**.
- Part 4 lists every problem we hit and its fix.

---

## Part 1 - The appliance pipeline

### 1.1 Hardware and base system (verified on a K36 R36S clone)

| | |
|---|---|
| SoC | Rockchip RK3326, 4× Cortex-A35 at 1.3 GHz (`performance` governor) |
| RAM | 736 MB total, **about 511 MB free** with ArkOS running |
| Screen | 640×480 DSI panel (ST7703 family), refresh 58.5 Hz |
| Controls | "GO-Super Gamepad" (SDL mapping in `assets/gamecontrollerdb.txt`) |
| Clock | **no RTC battery**: boots with the image's build date |
| Wi-Fi | not built in on this clone |
| Base image | [AeolusUX/ArkOS-K36](https://github.com/AeolusUX/ArkOS-K36) `ArkOS_K36_v2.0_08112025` |
| Base OS | Ubuntu 19.10, **Python 3.7.5**, **glibc 2.30**, libstdc++ up to `GLIBCXX_3.4.28` |
| Main user | `ark`, uid/gid **1002**, password-free `sudo` |
| Already installed | python3, SDL2 + SDL2_ttf + SDL2_mixer (KMS/DRM), alsa-utils (`aplay`), espeak-ng, PortMaster |
| Screen file | the release's **default `rf3536k4ka.dtb` works**; `ScreenFiles/Panel 5` gave a black screen |

To find which screen file a unit needs, compare the variants with
`tools/image/compare_panels.py <extracted BOOT folder>`. It prints each one's
resolution, refresh rate and panel start-up sequence. Match the refresh rate
and file size of the card the handheld shipped with.

### 1.2 SD card layout

```
offset 0        16 MiB   bootloader (u-boot, idbloader) - raw, no filesystem
offset 16 MiB   500 MB   p1 BOOT      FAT   kernel Image, uInitrd, *.dtb, extlinux/, logo.bmp
offset 516 MiB  8 GB     p2 root      ext4  Ubuntu 19.10 (ArkOS)
after p2        rest     p3 EASYROMS  exFAT created on FIRST BOOT by /root/firstboot.sh
```

The downloadable image is 9.1 GB (bootloader + p1 + p2). On its first boot,
`/root/firstboot.sh`:

1. regenerates SSH keys and uInitrd
2. repairs the GPT for the real card size (`gdisk`)
3. creates p3 across the rest of the card and formats it exFAT `EASYROMS`
4. copies the default folders from `/.rm_roms`
5. moves `/home/ark/fstab` to `/etc/fstab`
6. reboots

This step can take minutes with a blank-looking screen. **Don't power off
during it.**

### 1.3 Boot chain, and where the app takes over

```
u-boot -> BOOT/extlinux/extlinux.conf (FDT = screen file) -> Linux -> systemd
  -> emulationstation.service   (User=ark, normally runs emulationstation.sh)
       + drop-in /etc/systemd/system/emulationstation.service.d/10-chessos.conf
           ExecStart=            <- clears the original
           ExecStart=/opt/chessos/boot.sh
  -> boot.sh: mounts EASYROMS, then loops:  run the app
       exit 10 -> sudo systemctl poweroff
       exit 11 -> sudo systemctl reboot
       exit 0  -> run EmulationStation (Wi-Fi, updates, games); when it exits, back to the app
       other   -> show "stopped (code N)", open EmulationStation (never a dead end)
```

Why a **systemd drop-in**: nothing in ArkOS is edited. Deleting one file plus
`systemctl daemon-reload` gives stock ArkOS back. The service already starts
at the right moment, after `firstboot.service`, on tty1, with DRM access.

The app lives in **`/opt/<app>`** on the ext4 root, not on EASYROMS:
- first boot and the user can't wipe it
- Linux permissions work there (exFAT has none)
- it's still there if EASYROMS is damaged

Save data goes next to the app (`/opt/<app>/save`). Logs are copied to
**EASYROMS** (`/roms/chessos_log.txt`) so they can be read on a PC.

### 1.4 Building on Windows (`setup.ps1`)

| Command | What it does |
|---|---|
| `setup` | `.venv` + `requirements-dev.txt`; checks WSL + debugfs |
| `build` | app assets: puzzles, sprites, voice clips, sound effects, engines, boot logo; then `dist/` |
| `run` / `test` | run on the PC; scripted smoke test with screenshots |
| `image [-Panel N]` | download ArkOS-K36, then `work/chessos.img` via `tools/image/build_image.sh` (WSL) |
| `flash -Disk N` | write and verify the image (admin prompt, type the disk number twice) |
| `update -Disk N` | refresh the app on an already-flashed card, keeping save data (admin prompt) |
| `repair` | `chkdsk /f` on BOOT + EASYROMS after a power cut (admin prompt) |
| `ttsbench -Drive G` | copy the text-to-speech benchmark port to a card |

**WSL tools needed:** `e2fsprogs` (debugfs, e2fsck), `dosfstools` (fsck.vfat),
`python3-venv`. The builder creates `~/cosvenv` with `pyfatfs` itself.

### 1.5 How the image is built without root (`tools/image/build_image.sh`)

1. Copy `arkos.img` to `chessos.img`, then cut p2 out:
   `dd skip=516 count=8192 bs=1M` → `root.ext4`.
2. **`install_app.sh root.ext4 REPO`** writes the app into the ext4 file with
   **debugfs** (no mounting, no sudo):
   - `e2fsck -fy` first. A card that lost power has an unreplayed journal, and
     debugfs does not replay journals.
   - `mkdir` **only if missing**. debugfs `mkdir` on an existing directory
     leaves an orphaned inode, and the filesystem check then fails.
   - for each file: `rm`, `write`, then `sif uid/gid 1002`, and `sif mode 0100755`
     for scripts.
   - installs `boot.sh` and the systemd drop-in.
   - ends with `e2fsck -fn`. Any error stops the build.
3. Patch the **first-boot fstab** (`/home/ark/fstab`, which ArkOS later moves
   to `/etc/fstab`): add `nofail` and `x-systemd.device-timeout=10s` to the
   EASYROMS and Tools mounts, and `nofail` to `/boot`.
4. `dd` root.ext4 back in at 516 MiB (`conv=notrunc`).
5. **BOOT (FAT):** edited with `tools/image/edit_boot.py` (pyfatfs). It keeps
   the ArkOS logo as `logo_arkos.bmp`, installs `logo.bmp` / `logo_kernel.bmp`,
   and optionally switches the screen file (`--panel N`), then runs `fsck.vfat -n`.
   - Boot logos are **640×480, 8-bit palette, RLE8-compressed BMP**
     (`tools/build_bootlogo.py` writes them).
   - pyfatfs is case-sensitive while FAT names may be stored as 8.3 upper
     case (`EXTLINUX/EXTLINUX.CONF`), so paths are resolved case-insensitively.
   - pyfatfs corrupts a file when overwriting it with smaller data, so every
     write is **delete, then write**.

### 1.6 Flashing, updating and repairing cards (Windows)

All raw disk access needs Administrator rights. The scripts start an elevated
PowerShell (a UAC prompt) and refuse to run unless the target:
- is not the system or boot disk
- is a USB/SD/MMC bus disk
- still has **exactly the size you confirmed**

- **Flash** (`tools/card_write.ps1` → `sdcard.py write-image`):
  - `Clear-Disk`, then write the image **with the first 1 MiB last**, so
    Windows can't mount a half-written partition and block the write.
  - Then read everything back and compare the sha256.
  - (Removable cards can't be set "offline" on Windows; this ordering is the workaround.)
- **Update** (`tools/card_update.ps1`), typically 1–2 minutes of writing:
  1. `sdcard.py read-part` copies p2 to the PC.
  2. `install_app.sh` patches a copy.
  3. `sdcard.py write-diff` writes back **only the changed 4 MiB chunks**,
     each one read back and verified.
- **Repair** (`tools/card_repair.ps1`): `chkdsk /f /x` on BOOT and EASYROMS.

Call Python from elevated scripts with the plain call operator
(`& $Python script.py args *> log`). The `cmd /c "…"` form loses its quoting
in some elevated sessions ("The system cannot find the path specified").

---

## Part 2 - The app framework (reusable)

Anything that runs on ArkOS can be the app: a Python script, a native
binary, LÖVE, and so on. ChessOS uses **Python 3 + PySDL2**, the stack PortMaster's
own UI already uses on these devices, so nothing extra has to be installed.

### 2.1 Runtime skeleton (`device/chessos/`)

| File | Reuse as-is? | What it is |
|---|---|---|
| `main.py` | yes, rename strings | entry point. Adds `lib/` to the path, enables `faulthandler` (it dumps every thread's stack if no frame is drawn within 20 s), writes `crash.log` on exceptions, returns the exit code |
| `lib/sdl2/` | yes | PySDL2 (the copy PortMaster ships). Uses the system SDL2 on the device and `pysdl2-dll` on Windows |
| `app/gfx.py` | yes | logical 640×480 renderer, rounded rects and circles from one AA circle texture, cached text (TTF), sprites in a tiny zlib RGBA format (`.spr`, no SDL_image needed), render-target layers for static backgrounds |
| `app/inputs.py` | yes | SDL GameController + raw-joystick fallback (GO-Super layout), keyboard for PC testing, D-pad auto-repeat, SELECT+START = quit, optional A/B swap |
| `app/motion.py` | yes | springs, easing, keyframes, stagger (motion.dev's model, solved analytically) |
| `app/audio.py` | yes | SDL_mixer sound effects + voice queue (pre-rendered clips and a live Piper voice). Falls back to `aplay` |
| `app/core.py` | yes | main loop (60 fps target), scene stack (push/pop/replace/reset with fade), autopilot test harness, screenshots, exit codes, `frontend` flag |
| `app/ui.py` | yes | colour tokens, themes, Duolingo-style widgets (3D buttons, progress bar, speech bubble, banner, confetti) |
| `app/progress.py` | yes | JSON save file (atomic write), XP per day, streaks, settings, **clock sanity check** |
| `app/scenes/*` | app-specific | your screens |
| `app/chess.py`, `pgn.py`, `puzzles.py`, `engine.py`, `coach.py`, `board.py` | chess-specific | replace with your app's logic |

**Contract between `boot.sh` and the app:**
- **Environment:** `CHESSOS_DEVICE=1` (fullscreen, device paths),
  `CHESSOS_FRONTEND=1` (show Power off / Restart / ArkOS menus instead of
  "Exit"), and `SDL_GAMECONTROLLERCONFIG_FILE`.
- **Exit codes:** `10` = power off, `11` = restart, `0` = open EmulationStation.

### 2.2 Rules for code that runs on ArkOS

- **Python 3.7**: check with `vermin --no-tips -t=3.7- device/<app>`. Avoid the
  walrus operator, `list[str]` hints at runtime, `date.fromisoformat` (it is
  3.7+, but we keep 3.6-safe helpers) and f-string `=`.
- **Native binaries** must need at most `GLIBC_2.30` / `GLIBCXX_3.4.28`. Check with
  `objdump -T bin | grep -oE "GLIBC(XX)?_[0-9.]+" | sort -uV | tail`.
  Ubuntu 19.10 (eoan) arm64 `.deb` packages from `old-releases.ubuntu.com` match
  exactly. Stockfish 9 comes from there.
- **Python packages** with C code: use `cp37 … manylinux2014_aarch64` wheels and
  unzip them into a folder on `sys.path`; there is no pip on the device. The last
  onnxruntime with those wheels is **1.14.1** (ONNX IR ≤ 8, opset ≤ 18).
- **Memory**: about 500 MB free. Start helpers (TTS, engines) when a screen needs them
  and stop them when you leave it.
- **Never write to BOOT at runtime.** A power cut during a write can leave the
  handheld unbootable. Logs and user files go to EASYROMS (followed by `sync`) or `/opt/<app>`.
- **No RTC**: treat any date before your build date as wrong and ask the user
  (`progress.build_date()`, `data/build.json` written by `build_dist.py`).
- **Never block the frame loop**: run subprocesses (engines, TTS) with reader
  threads and poll them each frame.

### 2.3 Testing without the handheld

- `setup.ps1 run`: keyboard controls (arrows, Z = A, X = B, C = X, V = Y, Q/E = L1/R1, S = START, Tab = SELECT).
- **Autopilot**: `CHESSOS_AUTOPILOT="3.2|a|0.5|shot:home|eval:<python>|quit"` with steps
  separated by `|`. A number waits that many seconds, `shot:name` saves a screenshot,
  `eval:` runs Python with `app` in scope, and anything else is a button press.
  `tools/pc_test.sh` wraps it and converts the screenshots to PNG.
- **Linux device mode on a PC**: in WSL with `pysdl2-dll`, `SDL_VIDEODRIVER=offscreen
  CHESSOS_DEVICE=1` exercises the fullscreen and device paths.
- **Same engine versions on x86**: see `tools/tts/dryrun_x86.sh`. Test there before
  carrying a card to the device.

### 2.4 Voice and helpers (measured on the device, see `docs/tts-benchmark.md`)

| Engine | Load time | Speed once loaded | RAM | Use |
|---|---|---|---|---|
| Kokoro-82M on the **PC** | - | about 5× real time on the PC | - | pre-render every fixed line (Apache-2.0, ships in git) |
| Piper `lessac-low` on the device | 4.5 s | about real time | 130–180 MB | live sentences, kept running in the background |
| espeak-ng (system) | - | 50× real time | 6 MB | robotic fallback |
| Supertonic | 17 s | 1.4–2.9× slower than real time | 464 MB | ruled out |

The Piper protocol: run `piper --output_dir DIR`, write one line of text per
utterance, read back one `.wav` path per line. Newer requests make older,
still-pending ones obsolete (`audio.py` tracks tickets).

### 2.5 Theming

Colour tokens in `ui.py` are **lists**, and every screen imports the same list
objects, so `apply_theme(name)` recolours the whole UI instantly (`token[:] = new`).
A theme is: surfaces (bg, card, card_hi, border, text, sub, lock, frame, panel),
a main colour triple (main, shade, light) and five activity-grid colours.
Piece sets are sprites named `piece_<set>_<w|b><K|Q|R|B|N|P>`, drawn by
`tools/piece_sets.py`.

---

## Part 3 - Swap ChessOS for another app (checklist)

Say the new app is **"NoteOS"** in folder `noteos`.

1. **App folder.** Create `device/noteos/` with a `main.py` that honours the contract in 2.1.
   - Fastest route: copy `device/chessos/`, keep `lib/`, `app/gfx.py`, `inputs.py`,
     `motion.py`, `audio.py`, `core.py`, `ui.py`, `progress.py` and `main.py`.
   - Delete the chess modules and scenes, then write your own `scenes/` (start from `splash.py`).
   - Native app instead? Put the binary in `device/noteos/bin/linux-aarch64/` and make `main.py`
     (or `boot.sh` directly) run it, passing on its exit code.
2. **Rename the wiring.** These files mention `chessos` (`grep -rn chessos tools device/system`):

   | File | Change |
   |---|---|
   | `tools/build_dist.py` | the `copy_tree(... "chessos" ...)` source and target, the `build.json` path, launcher names, zip name |
   | `tools/image/install_app.sh` | `APP_SRC=…/ports/noteos`, every `/opt/chessos` → `/opt/noteos`, the drop-in file name |
   | `device/system/boot.sh` | `APP=/opt/noteos`, the log name, env variable names, on-screen text |
   | `device/system/10-chessos.conf` | rename to `10-noteos.conf`, `ExecStart=/opt/noteos/boot.sh` |
   | `tools/image/build_image.sh` | the `chessos.img` output name and messages (optional) |
   | `tools/build_bootlogo.py` | the logo artwork and text |
   | `setup.ps1` | the `build` steps your app needs (remove the puzzles, engines and voice steps you don't use) |
   | `device/ChessOS.sh` | the port launcher, if you also want "Option B: run as a port" |

3. **Assets.** Keep or replace fonts (`assets/fonts`), sprites (`tools/build_assets.py`)
   and sound effects (`tools/build_audio.py`). For voice, list your lines in the content
   module and run `build_audio.py` with Kokoro.
4. **Test on the PC**, then build: `setup.ps1 build`, `setup.ps1 test`, `setup.ps1 image`.
5. **Flash once**: `setup.ps1 flash -Disk N`. After that, iterate with
   `setup.ps1 update -Disk N` (about a minute per round, data kept).
6. **Switching an existing ChessOS card to the new app**: install `/opt/noteos`
   with the update flow, and make sure the old drop-in is removed (add
   `rm /etc/systemd/system/emulationstation.service.d/10-chessos.conf` to the
   debugfs script). Otherwise both drop-ins set `ExecStart`, and the file that
   sorts last wins.
7. **Back to stock ArkOS**: delete the drop-in file (from the device's terminal,
   or with debugfs on a copied root partition), then run `systemctl daemon-reload` or reboot.

### Porting to a different handheld or ArkOS image

Re-check every item in 1.1 and 1.2 against the new image:
- **Partition offsets**: `sfdisk -d image.img` (update `ROOT_OFF_MB` and the boot offset in `build_image.sh`).
- **The front-end service name and `User=`**: `debugfs -R "cat /etc/systemd/system/emulationstation.service"`.
- **The user's uid**: read `/etc/passwd`.
- **The first-boot script**: `/root/firstboot.sh`.
- **The fstab template** (`/home/ark/fstab`).
- **The C library and Python versions**.
- **The screen file**.

The debugfs helper `install_app.sh` and the disk tools do not depend on the
device, only on those values.

---

## Part 4 - Problems we hit and their fixes

| Symptom | Cause | Fix (now built in) |
|---|---|---|
| Black screen after the logo | wrong screen file (Panel 5, 60 Hz) | use the release's default `rf3536k4ka.dtb`; `-Panel N` to try others |
| Blinking cursor forever | first-boot exFAT format failed, then the `/roms` mount failed, then **emergency mode** (its prompt is on the serial console, so you only see a cursor) | `nofail` + timeout on the EASYROMS mounts; `boot.sh` formats p3 if it has **no** filesystem at all |
| "Full Repair Needed" on BOOT/EASYROMS | handheld powered off while writing | `setup.ps1 repair`; app never writes BOOT; power off from the app menu |
| Updater says "filesystem has errors" | ext4 journal not replayed after a power cut | `e2fsck -fy` on the working copy before debugfs |
| Filesystem check fails after an update | debugfs `mkdir` on an existing directory left an orphaned inode | `mkdir` only if the directory is missing |
| XP saved on "2025-07-17" | no RTC; the device boots with the ArkOS image's date | any date before the build date counts as wrong → ask the user |
| Supertonic: "Unsupported model IR version 9" | onnxruntime 1.14 (last py3.7 aarch64) | relabel IR 8 / opset 18 (`downgrade_onnx.py`, output verified identical) |
| Supertonic: `TypeError` on import | `list[str]` annotations on Python 3.7 | prepend `from __future__ import annotations` |
| Copy to EASYROMS stuck at 0 MB | exFAT marked dirty, robocopy retrying forever | `chkdsk /f`; robocopy with `/R:2 /W:2` |
| Windows refuses to take the card offline | removable media | write data first and the first 1 MiB last |
| Elevated script: "cannot find the path" | `cmd /c` quoting | call Python with `&` |
| Scripts break on the device | CRLF line endings from a Windows checkout | `.gitattributes`: `eol=lf`; `build_dist.py` converts too |
| Paths mangled when calling WSL from Git Bash | MSYS path conversion | `export MSYS_NO_PATHCONV=1` |
| UI froze for seconds | blocking espeak fallback in the voice queue | removed; live voice via a background Piper process |
| Screen freezes on start-up (diagnosis) | anything | `faulthandler` stack dump after 20 s, log copied to EASYROMS |
