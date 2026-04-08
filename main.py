#!/usr/bin/env python3
"""screen-ctrl – escape room media player.

Usage:
    python main.py [--config config.yml]
"""

import argparse
from datetime import datetime, timezone
import logging
import os
import signal
import sys

# Allow running directly from the screen-ctrl directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config as cfg_module
from app.mqtt_client import MQTTClient
from app.player import Player
from app.scene import SceneManager


def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO"), logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = log_cfg.get("file")
    if log_file:
        try:
            handlers.append(logging.FileHandler(log_file))
        except OSError as exc:
            print(f"WARNING: cannot open log file {log_file!r}: {exc}", file=sys.stderr)

    logging.basicConfig(level=level, format=fmt, handlers=handlers)


def main() -> None:
    parser = argparse.ArgumentParser(description="screen-ctrl – escape room media player")
    parser.add_argument("--config", default="config.yml", help="Path to YAML config file")
    args = parser.parse_args()

    config = cfg_module.load(args.config)
    setup_logging(config)

    log = logging.getLogger("screen-ctrl")
    log.info("screen-ctrl starting…")

    player = Player(config)
    scene = SceneManager(player, config)
    mqtt = MQTTClient(config, scene)

    def _publish_event(event: dict) -> None:
        mqtt.publish_status(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "source": "screen-ctrl",
                **event,
            }
        )

    player.set_event_handler(_publish_event)
    scene.set_event_handler(_publish_event)

    def _shutdown(sig, frame) -> None:
        log.info("Shutdown (signal %d)", sig)
        scene.stop()
        mqtt.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        log.info("Ready – waiting for MQTT commands on %s", config["mqtt"]["topic_control"])
        mqtt.start()  # blocks until disconnect / signal
    except Exception as exc:
        log.critical("Fatal error: %s", exc)
        player.stop_all()
        sys.exit(1)


if __name__ == "__main__":
    main()
