"""Scene orchestration.

A scene follows the sequence:
  1. Play video (fullscreen)
  2. When video ends naturally → show background image + start ambient loop

A per-scene cancel event ensures that a stop() or a new start_scene() call
cleanly aborts any pending transition, even if the video finishes at the
same time.
"""

import logging
import threading

logger = logging.getLogger(__name__)


class SceneManager:
    def __init__(self, player, config: dict, on_event=None) -> None:
        self._player = player
        self._config = config
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._on_event = on_event or (lambda _event: None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default(self, key: str):
        return self._config.get("scene", {}).get(key)

    def _emit_event(self, event: dict) -> None:
        try:
            self._on_event(event)
        except Exception:  # pragma: no cover - event reporting must not break scenes
            logger.exception("Failed to emit scene event: %s", event)

    def _transition(
        self,
        cancel: threading.Event,
        background: str | None,
        ambient: str | None,
    ) -> None:
        """Show background image and start ambient audio, unless cancelled."""
        if cancel.is_set():
            return
        logger.info("Scene transition → bg=%s  ambient=%s", background, ambient)
        if background:
            self._player.show_image(background)
        if ambient:
            self._player.play_ambient(ambient)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_event_handler(self, on_event) -> None:
        self._on_event = on_event or (lambda _event: None)

    def start_scene(
        self,
        video: str | None = None,
        background: str | None = None,
        ambient: str | None = None,
    ) -> None:
        """
        Start a full scene.  Falls back to configured defaults for any
        omitted parameter.
        """
        video = video or self._default("default_video")
        background = background or self._default("default_background")
        ambient = ambient or self._default("default_ambient")

        logger.info("start_scene: video=%s bg=%s ambient=%s", video, background, ambient)

        # Cancel any currently running scene
        with self._lock:
            self._cancel.set()
            cancel = threading.Event()
            self._cancel = cancel

        proc = self._player.play_video(video) if video else None

        if proc is None:
            # No video (or file missing) – jump straight to background
            self._transition(cancel, background, ambient)
            return

        def _watch() -> None:
            proc.wait()
            self._emit_event(
                {
                    "event": "video_finished",
                    "file": video,
                    "returncode": proc.returncode,
                    "cancelled": cancel.is_set(),
                }
            )
            # returncode == 0 → natural end; non-zero → killed/cancelled
            if proc.returncode == 0 and not cancel.is_set():
                self._transition(cancel, background, ambient)

        threading.Thread(target=_watch, daemon=True).start()

    def play_sound(self, filename: str) -> None:
        """Play a one-shot sound effect at any time."""
        self._player.play_effect(filename)

    def play_ambient(self, filename: str) -> None:
        """Start/replace ambient loop at any time."""
        self._player.play_ambient(filename)

    def stop_sound(self) -> None:
        """Interrupt currently playing one-shot sounds."""
        self._player.stop_effects()

    def stop_ambient(self) -> None:
        """Interrupt ambient loop without touching video/image."""
        self._player.stop_ambient()

    def stop_audio(self) -> None:
        """Interrupt all audio without touching video/image."""
        self._player.stop_audio()

    def stop(self) -> None:
        """Halt the current scene and all playback."""
        with self._lock:
            self._cancel.set()
            self._cancel = threading.Event()
        self._player.stop_all()
        logger.info("Scene stopped")
