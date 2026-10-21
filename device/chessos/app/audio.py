"""Sound effects + 'TTS' for ChessOS.

The R36S has no speech engine, so speech is made from clips pre-rendered on a
PC (tools/build_audio.py). speak("Excellent!") plays the matching clip;
speak_words([...]) chains clips, e.g. ["knight", "takes", "e5", "check"].
Lines without a clip (coach comments with piece/square names) are spoken live
by Piper when it is running (start_piper()).
Playback: SDL_mixer, else `aplay`, else silent.
"""
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import sdl2


class PiperService(object):
    """Piper kept running in the background: send a sentence, get a WAV path back.
    Loading the voice takes ~4.5 s on the R36S, then speech is about real time."""

    def __init__(self, exe, model, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        exe, model, out_dir = os.path.abspath(exe), os.path.abspath(model), os.path.abspath(out_dir)
        pdir = os.path.dirname(exe)
        env = dict(os.environ)
        if sys.platform != "win32":
            env["LD_LIBRARY_PATH"] = pdir + ":" + env.get("LD_LIBRARY_PATH", "")
        flags = 0x08000000 if sys.platform == "win32" else 0  # no console window
        self.proc = subprocess.Popen(
            [exe, "--model", model, "--espeak_data", os.path.join(pdir, "espeak-ng-data"),
             "--output_dir", out_dir, "-q"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            universal_newlines=True, bufsize=1, env=env, cwd=pdir, creationflags=flags)
        self.sent = 0
        self.received = 0
        self.results = queue.Queue()
        t = threading.Thread(target=self._reader)
        t.daemon = True
        t.start()

    def _reader(self):
        for line in self.proc.stdout:
            line = line.strip()
            if line.lower().endswith(".wav"):
                self.received += 1
                self.results.put((self.received, line))

    def say(self, text):
        try:
            self.proc.stdin.write(" ".join(text.split()) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError):
            return None
        self.sent += 1
        return self.sent

    def poll(self):
        out = []
        while True:
            try:
                out.append(self.results.get_nowait())
            except queue.Empty:
                return out

    def alive(self):
        return self.proc.poll() is None

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


def find_piper(base_dir):
    model = os.path.join(base_dir, "assets", "piper", "en_US-lessac-low.onnx")
    if sys.platform == "win32":
        exe = os.path.join(base_dir, "bin", "windows", "piper", "piper.exe")
    elif platform.machine().lower() in ("aarch64", "arm64"):
        exe = os.path.join(base_dir, "bin", "linux-aarch64", "piper", "piper")
    else:
        exe = shutil.which("piper") or ""
    if exe and os.path.exists(exe) and os.path.exists(model):
        return os.path.abspath(exe), os.path.abspath(model)
    return None, None


class Audio(object):
    def __init__(self, base_dir):
        self.base = base_dir
        self.voice_on = True
        self.sfx_on = True
        self.mixer = None
        self.chunks = {}
        self.queue = []
        self.voice_proc = None
        self.next_at = 0.0
        self.piper = None        # PiperService while Play vs Coach is open
        self.piper_dir = None
        self.waiting = {}        # ticket -> time requested
        self.ready = {}          # ticket -> wav path
        self.temp = None         # (chunk, path) of the last live clip
        vdir = os.path.join(base_dir, "assets", "voice")
        try:
            with open(os.path.join(vdir, "index.json"), encoding="utf-8") as f:
                self.index = json.load(f)
        except Exception:
            self.index = {}
        self.vdir = vdir
        self.espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        self.aplay = shutil.which("aplay")
        try:
            if sdl2.SDL_InitSubSystem(sdl2.SDL_INIT_AUDIO) != 0:
                raise RuntimeError("no audio")
            import sdl2.sdlmixer as mix
            if mix.Mix_OpenAudio(44100, mix.MIX_DEFAULT_FORMAT, 2, 1024) != 0:
                raise RuntimeError("Mix_OpenAudio failed")
            mix.Mix_AllocateChannels(10)
            mix.Mix_ReserveChannels(1)  # channel 0 = voice
            self.mixer = mix
        except Exception as e:
            print("audio: SDL_mixer unavailable (%s), using %s" % (e, "aplay" if self.aplay else "no sound"))

    # ---- low level -------------------------------------------------------------
    def _chunk(self, path):
        if self.piper_dir and path.startswith(self.piper_dir):
            return self.mixer.Mix_LoadWAV(path.encode("utf-8"))  # one-off, freed after use
        c = self.chunks.get(path)
        if c is None and self.mixer:
            c = self.mixer.Mix_LoadWAV(path.encode("utf-8"))
            self.chunks[path] = c
        return c

    def _play(self, path, channel=-1):
        if not os.path.exists(path):
            return
        if self.mixer:
            c = self._chunk(path)
            if c:
                if channel == 0:
                    self._free_temp()
                    if self.piper_dir and path.startswith(self.piper_dir):
                        self.temp = (c, path)
                self.mixer.Mix_PlayChannel(channel, c, 0)
        elif self.aplay:
            p = subprocess.Popen([self.aplay, "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if channel == 0:
                self.voice_proc = p
        elif sys.platform == "win32" and channel == 0:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def _free_temp(self):
        if self.temp:
            c, path = self.temp
            self.temp = None
            if self.mixer:
                self.mixer.Mix_HaltChannel(0)
                self.mixer.Mix_FreeChunk(c)
            try:
                os.remove(path)
            except OSError:
                pass

    def _voice_busy(self):
        if self.mixer:
            return self.mixer.Mix_Playing(0) != 0
        if self.voice_proc is not None:
            return self.voice_proc.poll() is None
        return False

    # ---- live voice (Piper) ----------------------------------------------------------
    def start_piper(self):
        """Start the live voice in the background (used by Play vs Coach)."""
        if self.piper is not None and self.piper.alive():
            return True
        exe, model = find_piper(self.base)
        if not exe:
            return False
        try:
            self.piper_dir = os.path.join(tempfile.gettempdir(), "chessos_tts")
            self.piper = PiperService(exe, model, self.piper_dir)
            return True
        except Exception as e:
            print("audio: piper failed:", e)
            self.piper = None
            return False

    def stop_piper(self):
        if self.piper is not None:
            self.piper.close()
            self.piper = None
        self.queue = [q for q in self.queue if not isinstance(q, int)]

    def live_ready(self):
        return self.piper is not None and self.piper.alive()

    # ---- API ---------------------------------------------------------------------
    def sfx(self, name):
        if self.sfx_on:
            self._play(os.path.join(self.base, "assets", "sfx", name + ".wav"))

    def has_clip(self, text):
        return text in self.index

    def _clip_path(self, text):
        name = self.index.get(text)
        if name:
            return os.path.join(self.vdir, name)
        return None

    def speak(self, text, interrupt=True):
        self.speak_words([text], interrupt)

    def speak_words(self, words, interrupt=True):
        """Each word/line plays its Kokoro clip; anything without a clip goes to
        Piper (if running) and is played as soon as it's synthesized."""
        if not self.voice_on:
            return
        if interrupt:
            self.stop_voice()
        for w in words:
            p = self._clip_path(w)
            if p:
                self.queue.append(p)
            elif self.live_ready():
                ticket = self.piper.say(w)
                if ticket:
                    self.queue.append(ticket)
                    self.waiting[ticket] = time.time()

    def stop_voice(self):
        for q in self.queue:
            if isinstance(q, int):
                self.waiting.pop(q, None)
        self.queue = []
        if self.mixer:
            self.mixer.Mix_HaltChannel(0)
        elif self.voice_proc is not None and self.voice_proc.poll() is None:
            self.voice_proc.terminate()

    def update(self):
        if self.piper is not None:
            for ticket, path in self.piper.poll():
                if ticket in self.waiting:
                    self.waiting.pop(ticket)
                    self.ready[ticket] = path
                else:  # superseded by a newer comment
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        if not self.queue or self._voice_busy() or time.time() < self.next_at:
            return
        head = self.queue[0]
        if isinstance(head, int):
            if head in self.ready:
                self.queue[0] = self.ready.pop(head)
            elif time.time() - self.waiting.get(head, 0) > 25 or not self.live_ready():
                self.queue.pop(0)  # took too long: skip it
                self.waiting.pop(head, None)
                return
            else:
                return
        self._play(self.queue.pop(0), channel=0)
        self.next_at = time.time() + 0.03

    def quit(self):
        self.stop_piper()
        self._free_temp()
        if self.mixer:
            self.mixer.Mix_CloseAudio()
