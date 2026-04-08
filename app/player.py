"""Media player layer.

Primary backend: python-mpv (libmpv bindings).
Fallback backend: mpv CLI subprocesses (works when libmpv is missing).
"""

import logging
import os
import subprocess
import threading

try:
    import mpv as _mpv  # type: ignore
    _MPV_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    _mpv = None
    _MPV_IMPORT_ERROR = exc

logger = logging.getLogger(__name__)


class _PlaybackToken:
    """Scene-compatible wait token (similar to subprocess handle subset)."""

    def __init__(self) -> None:
        self._done = threading.Event()
        self.returncode: int | None = None

    def _finish(self, returncode: int) -> None:
        if not self._done.is_set():
            self.returncode = returncode
            self._done.set()

    def wait(self) -> None:
        self._done.wait()


class Player:
    def __init__(self, config: dict, on_event=None) -> None:
        self._cfg = config
        self._lock = threading.Lock()
        self._on_event = on_event or (lambda _event: None)

        self._use_python_mpv = _mpv is not None

        # Shared state
        self._video_token: _PlaybackToken | None = None
        self._video_cancel: threading.Event = threading.Event()

        # python-mpv backend state
        self._video_player = None
        self._ambient_player = None
        self._effect_players: list = []

        # subprocess backend state
        self._video_proc: subprocess.Popen | None = None
        self._image_proc: subprocess.Popen | None = None
        self._ambient_proc: subprocess.Popen | None = None
        self._effect_procs: list[subprocess.Popen] = []

        if self._use_python_mpv:
            logger.info("Player backend: python-mpv")
        else:
            logger.warning(
                "Player backend fallback: subprocess mpv (reason: %s)",
                _MPV_IMPORT_ERROR,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _media_path(self, sub_key: str, filename: str) -> str:
        base = self._cfg["media"]["base_path"]
        sub = self._cfg["media"][sub_key]
        return os.path.join(base, sub, filename)

    def _volume(self) -> int:
        return int(self._cfg["mpv"].get("volume", 80))

    def _emit_event(self, event: dict) -> None:
        try:
            self._on_event(event)
        except Exception:
            logger.exception("Failed to emit player event: %s", event)

    def set_event_handler(self, on_event) -> None:
        self._on_event = on_event or (lambda _event: None)

    @staticmethod
    def _kill_proc(proc: subprocess.Popen | None) -> None:
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    # python-mpv helpers

    def _new_player(self, audio_only: bool = False):
        player = _mpv.MPV(
            log_handler=lambda _lev, comp, msg: logger.debug("[mpv/%s] %s", comp, msg.strip()),
            loglevel="warn",
        )
        player.volume = self._volume()
        if audio_only:
            player["vid"] = "no"
        elif self._cfg["mpv"].get("fullscreen", True):
            player.fullscreen = True
        return player

    @staticmethod
    def _stop_player(player) -> None:
        if player is None:
            return
        try:
            player.terminate()
        except Exception:
            pass

    # subprocess helpers

    def _fullscreen_flag(self) -> list[str]:
        return ["--fullscreen"] if self._cfg["mpv"].get("fullscreen", True) else []

    def _mpv_cmd(self, *extra: str) -> list[str]:
        return (
            ["mpv", "--no-terminal", "--really-quiet"]
            + self._fullscreen_flag()
            + [f"--volume={self._volume()}"]
            + list(extra)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def play_video(self, filename: str) -> "_PlaybackToken | None":
        path = self._media_path("videos_dir", filename)
        if not os.path.exists(path):
            logger.error("Video not found: %s", path)
            return None

        if self._use_python_mpv:
            return self._play_video_mpv(filename, path)
        return self._play_video_subprocess(filename, path)

    def _play_video_mpv(self, filename: str, path: str) -> _PlaybackToken:
        token = _PlaybackToken()
        cancel = threading.Event()

        with self._lock:
            self._stop_player(self._video_player)
            if self._video_token:
                self._video_token._finish(1)
            self._video_cancel = cancel
            player = self._new_player(audio_only=False)
            self._video_player = player
            self._video_token = token

        player.play(path)
        logger.info("play_video: %s", filename)
        self._emit_event({"event": "video_started", "file": filename})

        def _watch() -> None:
            player.wait_for_playback()
            rc = 1 if cancel.is_set() else 0
            token._finish(rc)
            self._emit_event(
                {
                    "event": "video_finished",
                    "file": filename,
                    "returncode": rc,
                    "cancelled": cancel.is_set(),
                }
            )

        threading.Thread(target=_watch, daemon=True).start()
        return token

    def _play_video_subprocess(self, filename: str, path: str) -> _PlaybackToken:
        token = _PlaybackToken()
        cancel = threading.Event()

        cmd = self._mpv_cmd(path)
        with self._lock:
            self._video_cancel.set()
            self._kill_proc(self._video_proc)
            self._kill_proc(self._image_proc)
            self._image_proc = None
            if self._video_token:
                self._video_token._finish(1)
            self._video_cancel = cancel
            proc = subprocess.Popen(cmd)
            self._video_proc = proc
            self._video_token = token

        logger.info("play_video: %s", filename)
        self._emit_event({"event": "video_started", "file": filename})

        def _watch() -> None:
            proc.wait()
            natural = (proc.returncode == 0) and (not cancel.is_set())
            rc = 0 if natural else 1
            token._finish(rc)
            self._emit_event(
                {
                    "event": "video_finished",
                    "file": filename,
                    "returncode": rc,
                    "cancelled": cancel.is_set(),
                }
            )

        threading.Thread(target=_watch, daemon=True).start()
        return token

    def show_image(self, filename: str) -> None:
        path = self._media_path("images_dir", filename)
        if not os.path.exists(path):
            logger.error("Image not found: %s", path)
            return

        if self._use_python_mpv:
            with self._lock:
                self._stop_player(self._video_player)
                if self._video_token:
                    self._video_token._finish(1)
                player = self._new_player(audio_only=False)
                player["image-display-duration"] = "inf"
                player.loop = True
                player.volume = 0
                self._video_player = player
                self._video_token = None
            player.play(path)
        else:
            cmd = self._mpv_cmd("--image-display-duration=inf", "--loop", "--volume=0", path)
            with self._lock:
                self._video_cancel.set()
                self._kill_proc(self._video_proc)
                self._kill_proc(self._image_proc)
                if self._video_token:
                    self._video_token._finish(1)
                self._video_proc = None
                self._video_token = None
                self._image_proc = subprocess.Popen(cmd)

        logger.info("show_image: %s", filename)

    def play_ambient(self, filename: str) -> None:
        path = self._media_path("audio_dir", filename)
        if not os.path.exists(path):
            logger.error("Ambient not found: %s", path)
            return

        if self._use_python_mpv:
            with self._lock:
                self._stop_player(self._ambient_player)
                player = self._new_player(audio_only=True)
                player.loop_playlist = "inf"
                self._ambient_player = player
            player.play(path)
        else:
            cmd = [
                "mpv",
                "--no-terminal",
                "--really-quiet",
                "--no-video",
                "--loop-playlist=inf",
                f"--volume={self._volume()}",
                path,
            ]
            with self._lock:
                self._kill_proc(self._ambient_proc)
                self._ambient_proc = subprocess.Popen(cmd)

        logger.info("play_ambient: %s", filename)
        self._emit_event({"event": "ambient_started", "file": filename})

    def play_effect(self, filename: str) -> None:
        path = self._media_path("audio_dir", filename)
        if not os.path.exists(path):
            logger.error("Effect not found: %s", path)
            return

        logger.info("play_effect: %s", filename)
        self._emit_event({"event": "sound_started", "file": filename})

        if self._use_python_mpv:
            player = self._new_player(audio_only=True)
            with self._lock:
                self._effect_players.append(player)
            player.play(path)

            def _watch_effect() -> None:
                player.wait_for_playback()
                self._emit_event({"event": "sound_finished", "file": filename, "returncode": 0})
                self._stop_player(player)
                with self._lock:
                    try:
                        self._effect_players.remove(player)
                    except ValueError:
                        pass

            threading.Thread(target=_watch_effect, daemon=True).start()
            return

        cmd = [
            "mpv",
            "--no-terminal",
            "--really-quiet",
            "--no-video",
            f"--volume={self._volume()}",
            path,
        ]
        proc = subprocess.Popen(cmd)
        with self._lock:
            self._effect_procs = [p for p in self._effect_procs if p.poll() is None]
            self._effect_procs.append(proc)

        def _watch_proc() -> None:
            proc.wait()
            rc = proc.returncode if proc.returncode is not None else 1
            self._emit_event({"event": "sound_finished", "file": filename, "returncode": rc})
            with self._lock:
                self._effect_procs = [p for p in self._effect_procs if p is not proc and p.poll() is None]

        threading.Thread(target=_watch_proc, daemon=True).start()

    def stop_ambient(self) -> None:
        if self._use_python_mpv:
            with self._lock:
                self._stop_player(self._ambient_player)
                self._ambient_player = None
        else:
            with self._lock:
                self._kill_proc(self._ambient_proc)
                self._ambient_proc = None
        logger.info("Ambient stopped")
        self._emit_event({"event": "ambient_stopped"})

    def stop_effects(self) -> None:
        if self._use_python_mpv:
            with self._lock:
                players, self._effect_players = self._effect_players, []
            for p in players:
                self._stop_player(p)
        else:
            with self._lock:
                procs, self._effect_procs = self._effect_procs, []
            for p in procs:
                self._kill_proc(p)

        logger.info("All one-shot sounds stopped")
        self._emit_event({"event": "sound_stopped"})

    def stop_audio(self) -> None:
        self.stop_ambient()
        self.stop_effects()

    def stop_all(self) -> None:
        self._video_cancel.set()

        if self._use_python_mpv:
            with self._lock:
                self._stop_player(self._video_player)
                if self._video_token:
                    self._video_token._finish(1)
                self._stop_player(self._ambient_player)
                players, self._effect_players = self._effect_players, []
                self._video_player = None
                self._video_token = None
                self._ambient_player = None
            for p in players:
                self._stop_player(p)
        else:
            with self._lock:
                self._kill_proc(self._video_proc)
                self._kill_proc(self._image_proc)
                if self._video_token:
                    self._video_token._finish(1)
                self._kill_proc(self._ambient_proc)
                procs, self._effect_procs = self._effect_procs, []
                self._video_proc = None
                self._image_proc = None
                self._video_token = None
                self._ambient_proc = None
            for p in procs:
                self._kill_proc(p)

        logger.info("All playback stopped")

    def set_volume(self, value: int | float) -> None:
        new_vol = max(0, min(100, int(value)))
        self._cfg["mpv"]["volume"] = new_vol

        if self._use_python_mpv:
            with self._lock:
                active = [self._video_player, self._ambient_player] + list(self._effect_players)
            for p in active:
                if p is not None:
                    try:
                        p.volume = new_vol
                    except Exception:
                        pass

        logger.info("Volume set to %d", new_vol)
