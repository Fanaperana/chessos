# Developer tutorial: put your own app on an R36S

This repo can turn an R36S-class handheld into **a device that boots straight
into your app**: "ChessOS" today, "NoteOS" or anything else tomorrow. One
setting picks the app (`appliance.json`), and one command puts it on a card
(`.\setup.ps1 deploy`).

- **Tutorial 1:** a Python + SDL2 app, from zero to hardware in about 15 minutes.
- **Tutorial 2:** a native app (Rust, C/C++, Go, Zig…).
- **Tutorial 3:** what running a **Tauri** app would take, and better alternatives.
- **Reference:** the app contract, the commands, and where things live.

How it works under the hood (boot chain, image builder, every problem we hit):
[APPLIANCE-GUIDE.md](APPLIANCE-GUIDE.md).

---

## 0. One-time setup (Windows 10/11)

1. Install **Python 3.9+** (python.org) and **Git**.
2. Install **WSL** with Ubuntu, then the disk tools it needs. WSL is only used
   for building and updating whole-OS cards:
   ```powershell
   wsl --install -d Ubuntu-22.04
   wsl -d Ubuntu-22.04 -- sudo apt install -y e2fsprogs dosfstools python3-venv
   ```
3. Get the repo and its PC tools:
   ```powershell
   git clone https://github.com/Fanaperana/chessos
   cd chessos
   .\setup.ps1 setup
   ```
4. Hardware: an R36S / K36 clone and an SD card reader. A second SD card is
   handy, so your working card stays untouched.

---

## 1. Your first app (Python + SDL2), about 15 minutes

**Create it.** This copies the shared framework (graphics, input, animation,
sound, UI widgets, scene stack, save file) and a starter screen, then makes it
the active app:

```powershell
.\setup.ps1 new-app -Name noteos -Title NoteOS
```

You get `device\noteos\`:

```
main.py                 entry point (don't need to touch it)
app.json                title, env-var prefix, boot-logo tagline
app\scenes\hello.py     your first screen  <- edit this
app\core.py gfx.py inputs.py motion.py audio.py ui.py progress.py   the framework
lib\sdl2\               PySDL2 (uses the system SDL2 on the device)
assets\fonts\ sfx\ gamecontrollerdb.txt sprites\circle.spr
```

**Run it on the PC** (keyboard: arrows, Z = A, X = B, S or Esc = START):

```powershell
.\setup.ps1 run
```

**Change something.** A screen is a `Scene` with `update(dt, actions)` and
`draw(g, dt)`. `actions` holds button names: `up down left right a b x y l1 r1
l2 r2 start select`. For example, add a counter to `hello.py`:

```python
class Hello(Scene):
    def enter(self):
        self.count = 0
        self.pop = motion.Value(1)                 # animated number

    def update(self, dt, actions):
        for a in actions:
            if a == "a":
                self.count += 1
                self.pop.set(1.4).spring(1, "bouncy")   # motion.dev-style spring
                self.app.audio.sfx("correct")

    def draw(self, g, dt):
        g.text(str(self.count), 320, 240, 64, GREEN[0], 900,
               align="c", valign="m", scale=self.pop.get())
```

Useful framework calls:
- **`g`:** `g.rect / rrect / circle / text / text_block / draw_sprite / button3d`.
- **`self.app`:** `self.app.push(Scene)` / `pop()` / `replace()`, `self.app.audio.sfx/speak`,
  and `self.app.progress` (JSON save: `data`, `save()`, `add_xp()`, `streak()`).
- **`self.app.exit_code`:** set it to `10` (power off) or `11` (restart), then
  call `self.app.quit()`. On a whole-OS card, `self.app.frontend` is True.

**Check that it starts cleanly**, then make sure it still runs on the device's Python 3.7:

```powershell
.\setup.ps1 test
.venv\Scripts\pip install vermin
.venv\Scripts\vermin --no-tips -t=3.7- device\noteos
```

**Put it on a card:**

```powershell
.\setup.ps1 deploy
```

The wizard asks which app, then how to install it:

| Choice | What happens | Needs |
|---|---|---|
| **1 Whole OS** | downloads ArkOS-K36, builds `work\noteos.img` with your app as the boot program, erases a card and writes it (verified) | WSL, admin prompt, about 15 min the first time |
| **2 App only** | copies the app into the **Ports** menu of a card that already runs ArkOS (plus an optional "boot mode" toggle) | nothing else, about 1 min |
| **3 Update** | refreshes the app on a card made with choice 1, keeping everything else | WSL, admin prompt, about 5 min |

The fastest loop while developing: **2** onto your everyday ArkOS card
(Ports → NoteOS). Use **1** once you want the real "boots into my app" device,
then **3** for each update after that.

**Back to ChessOS** at any time: `.\setup.ps1 use -Name chessos`.

---

## 2. A native app (Rust, C/C++, Go, Zig…)

```powershell
.\setup.ps1 new-app -Name myapp -Title MyApp -Template native
```

This gives you `device\myapp\start` (a launcher script) and an empty `bin\`.
The boot session runs `start`, so any language works, as long as:

1. **It's aarch64 Linux and needs at most glibc 2.30 and `GLIBCXX_3.4.28`** (ArkOS is Ubuntu 19.10).
   - **Rust:** `cargo install cargo-zigbuild`, then
     `cargo zigbuild --release --target aarch64-unknown-linux-gnu.2.30`
     (zig pins the glibc version).
   - **C/C++:** `zig cc -target aarch64-linux-gnu.2.30`, or build inside an
     `arm64 ubuntu:19.10` container (old-releases mirrors).
   - **Check it:**
     `objdump -T bin/myapp | grep -oE "GLIBC(XX)?_[0-9.]+" | sort -uV | tail -3`
2. **It draws with SDL2 (KMS/DRM)**: there is no X11 or Wayland. Link
   dynamically against the system `libSDL2-2.0.so.0`, create a fullscreen
   window, and SDL picks the KMSDRM backend. Read the gamepad through SDL's
   GameController API: `SDL_GAMECONTROLLERCONFIG_FILE` points at
   `assets/gamecontrollerdb.txt`. Copy it from `device\chessos\assets\`.
3. **It fits about 500 MB of RAM** and is gentle on a 1.3 GHz Cortex-A35.
4. **It ends with the contract exit codes** (`10` power off, `11` restart, `0` ArkOS menus).

Copy the binary to `device\myapp\bin\myapp`, then `.\setup.ps1 deploy` as above.
Other ready-made routes that already run on these devices: **LÖVE** (Lua) and
**Godot** (via PortMaster's runtimes).

---

## 3. What would it take to run a Tauri app?

**Short answer: it's possible in principle, but a poor fit for this device,
and I haven't tried it on one.** Here is the full picture, so you can decide.

### Why it doesn't just work

| Tauri needs | ArkOS on the R36S has |
|---|---|
| A web view: **WebKitGTK** (`webkit2gtk-4.1` for Tauri v2, `-4.0` for Tauri v1) | no WebKitGTK; Ubuntu 19.10 offers only 4.0 (2.28), so **Tauri v2 is out**, and only legacy Tauri v1 could link |
| A display server (GTK on **X11 or Wayland**) | neither: apps draw straight to the screen (KMS/DRM) |
| GStreamer for media and audio in the web view | not installed |
| A browser engine's memory (WebKit's web process alone is often 150–250 MB) | about 500 MB free in total |
| GPU-accelerated compositing | the Mali GPU driver is for KMS/GLES apps, so WebKit under X11 would fall back to software rendering |
| Keyboard, mouse or touch | a gamepad; the WebKitGTK of that era has no Gamepad API |

### If you still want to try (Tauri v1)

1. **Build environment:** an `arm64 ubuntu:19.10` Docker container (Docker
   Desktop with QEMU), with apt pointed at `old-releases.ubuntu.com`. Install
   `libwebkit2gtk-4.0-dev libgtk-3-dev librsvg2-dev` and Rust, then
   `cargo tauri build --bundles none` on a **Tauri v1** project.
   Building natively in the container avoids sysroot cross-compile problems,
   but it is slow under emulation.
2. **Window:** in `tauri.conf.json` set `fullscreen: true`, `decorations: false`,
   `resizable: false`, and a 640×480 layout.
3. **Runtime on the device** is the hard part. You must add **Xorg**
   (`xserver-xorg-core`, the `modesetting` driver, `xinit`), **WebKitGTK 4.0**
   with its dependencies, and **GStreamer** base plugins. That is a few hundred
   packages and roughly 300–400 MB. Two ways:
   - **Bundle the libraries:** put every `.so` file from the container in
     `/opt/myapp/lib` (the AppImage idea) and set `LD_LIBRARY_PATH` in `start`.
     Xorg itself still has to be installed system-wide.
   - **Install them on the device** with `apt` through a USB network adapter.
     This K36 clone has no Wi-Fi, and Ubuntu 19.10's repos only exist on
     `old-releases`.
4. **`start` script:** `xinit /opt/myapp/bin/myapp -- :0 vt1 -nocursor` (no window manager).
5. **Controls:** run PortMaster's `gptokeyb`, already on ArkOS cards, to turn
   the gamepad into keyboard keys, and handle those keys in your web UI.
6. **Expect:** a cold start of several seconds, low frame rates for CSS
   animations in software rendering, and a high memory risk. A blocking
   problem: Tauri v1 is legacy, and v2 would need a newer base OS. That means
   a Debian 12 based image such as dArkOS, which users report to be unreliable
   on K36 clones.

### What I'd use instead

| You like… | Use | Why it fits the R36S |
|---|---|---|
| Building UIs quickly, the web way | **Python + SDL2** (this framework) | already installed, 60 fps on the device, the whole ChessOS UI is built with it |
| Rust and declarative UI like Tauri's front end | **[Slint](https://slint.dev)** with its `linuxkms` backend | made for embedded Linux, draws straight to DRM (no X11/Wayland), small memory use; a `native`-template app |
| Rust, full control | **Rust + SDL2** (`sdl2` crate) | a single binary; cross-compile with `cargo zigbuild` |
| A game engine and editor | **Godot** (PortMaster runtime) or **LÖVE** | both already used on these handhelds |
| Keeping your Svelte/Tauri UI | run it on the PC and treat the handheld as a client | the device stays fast; needs a network link |

If you'd like to try one of these as a second app, `new-app -Template native`
plus the checklist in section 2 is the starting point.

---

## 4. Reference

### The app contract

| | |
|---|---|
| Install location | `/opt/<app>` on the ext4 root (owned by `ark`, uid 1002, password-free `sudo`) |
| Started by | `/opt/<app>/boot.sh`, generated from `device/system/boot.sh.in`. It runs `start` if present, else `python3 main.py` |
| Environment | `APPLIANCE_DEVICE=1`, `APPLIANCE_FRONTEND=1`, `APPLIANCE_APP=<app>`, plus `<ENV>_DEVICE` and `<ENV>_FRONTEND`, and `SDL_GAMECONTROLLERCONFIG_FILE` |
| Exit codes | `10` power off · `11` restart · `0` open ArkOS menus (Wi-Fi, updates), then back to your app · anything else = treated as a crash, ArkOS menus |
| Screen | 640×480 · KMS/DRM · SDL2 |
| Logs | stdout/stderr → `/opt/<app>/log.txt`, copied to **EASYROMS/`<app>`_log.txt** (readable on a PC) |
| Don'ts | never write to the BOOT partition; don't trust the clock (no RTC); don't block for long without drawing |

### Files you own vs. shared plumbing

| Path | Purpose |
|---|---|
| `appliance.json` | **the** setting: which app the build uses (`use` / `new-app` write it) |
| `device/<app>/` | your app; `app.json` = its title, env prefix, tagline |
| `device/<app>/build.ps1` | optional build hook (asset generation), run by `setup.ps1 build`; not copied to the card |
| `device/<app>/assets/bootlogo.png` | optional custom boot logo (any size, converted to 640×480 RLE8 BMP) |
| `device/system/*.in` | templates: boot session, systemd drop-in, port launchers (`@APP@ @TITLE@ @ENV@ @TAGLINE@`) |
| `tools/image/` | root-free image builder and installer (debugfs, pyfatfs) |
| `tools/card_*.ps1`, `tools/sdcard.py` | flash, update, repair (admin) with safety checks |

### Commands

```text
.\setup.ps1 deploy                       guided build + install (start here)
.\setup.ps1 new-app -Name x -Title X [-Template python-sdl|native]
.\setup.ps1 use -Name x                  switch the active app
.\setup.ps1 run | test | build
.\setup.ps1 image [-Panel N] | flash -Disk N | update -Disk N | install [-Drive G] | repair
```
