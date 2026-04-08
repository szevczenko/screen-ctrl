"""Configuration loader with sane defaults."""

import os
import logging

import yaml

logger = logging.getLogger(__name__)

DEFAULTS = {
    "mqtt": {
        "broker": "localhost",
        "port": 1883,
        "topic_control": "escape/control",
        "topic_status": "escape/status",
        "keepalive": 60,
    },
    "media": {
        "base_path": "/home/pi",
        "videos_dir": "videos",
        "images_dir": "images",
        "audio_dir": "audio",
    },
    "scene": {
        "default_video": "intro.mp4",
        "default_background": "tlo.png",
        "default_ambient": "ambient.mp3",
    },
    "mpv": {
        "fullscreen": True,
        "volume": 80,
    },
    "logging": {
        "level": "INFO",
        "file": None,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load(path: str = "config.yml") -> dict:
    """Load config from YAML file, merging with defaults."""
    # Deep-copy defaults so nested dicts are independent
    config = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        config = _deep_merge(config, user)
        logger.debug("Config loaded from %s", path)
    else:
        logger.warning("Config file not found at %s – using defaults", path)

    return config
