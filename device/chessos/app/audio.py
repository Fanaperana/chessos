"""Sound effects + 'TTS' for ChessOS.

The R36S has no speech engine, so speech is made from clips pre-rendered on a
PC (tools/build_audio.py). speak("Excellent!") plays the matching clip;
speak_words([...]) chains clips, e.g. ["knight", "takes", "e5", "check"].
If a line has no clip and espeak/espeak-ng exists on the device, it is used.
Playback: SDL_mixer, else `aplay`, else silent.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import sdl2


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
                self.mixer.Mix_PlayChannel(channel, c, 0)
        elif self.aplay:
            p = subprocess.Popen([self.aplay, "-q", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if channel == 0:
                self.voice_proc = p
        elif sys.platform == "win32" and channel == 0:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)

    def _voice_busy(self):
        if self.mixer:
            return self.mixer.Mix_Playing(0) != 0
        if self.voice_proc is not None:
            return self.voice_proc.poll() is None
        return False

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
        if self.espeak:
            try:
                fd, path = tempfile.mkstemp(suffix=".wav")
                os.close(fd)
                subprocess.call([self.espeak, "-s", "150", "-w", path, text],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                return path
            except Exception:
                return None
        return None

    def speak(self, text, interrupt=True):
        self.speak_words([text], interrupt)

    def speak_words(self, words, interrupt=True):
        if not self.voice_on:
            return
        if interrupt:
            self.stop_voice()
        for w in words:
            p = self._clip_path(w)
            if p:
                self.queue.append(p)

    def stop_voice(self):
        self.queue = []
        if self.mixer:
            self.mixer.Mix_HaltChannel(0)
        elif self.voice_proc is not None and self.voice_proc.poll() is None:
            self.voice_proc.terminate()

    def update(self):
        if self.queue and not self._voice_busy() and time.time() >= self.next_at:
            self._play(self.queue.pop(0), channel=0)
            self.next_at = time.time() + 0.03

    def quit(self):
        if self.mixer:
            self.mixer.Mix_CloseAudio()
