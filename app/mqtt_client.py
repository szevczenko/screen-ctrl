"""MQTT client – bridges Node-RED commands to SceneManager.

Supported MQTT messages on topic ``escape/control`` (JSON or plain text):

  {"cmd": "start_scene"}
  {"cmd": "start_scene", "video": "intro.mp4", "background": "tlo.png", "ambient": "ambient.mp3"}
  {"cmd": "play_sound",  "file": "scare.mp3"}
    {"cmd": "play_ambient", "file": "ambient.mp3"}
    {"cmd": "play_audio", "mode": "once|ambient", "file": "audio.mp3"}
    {"cmd": "stop_sound"}
    {"cmd": "stop_ambient"}
    {"cmd": "stop_audio"}
  {"cmd": "set_volume",  "value": 70}
  {"cmd": "stop"}

Plain-text commands (e.g. just ``stop``) are also accepted.

Status events are published to topic ``escape/status`` (configurable)
for lifecycle notifications such as ``video_finished`` and ``sound_finished``.
"""

import json
import logging

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self, config: dict, scene_manager) -> None:
        self._cfg = config["mqtt"]
        self._scene = scene_manager

        self._client = mqtt.Client(protocol=mqtt.MQTTv311)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=2, max_delay=30)

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topic = self._cfg["topic_control"]
            client.subscribe(topic)
            logger.info("MQTT connected – subscribed to %s", topic)
        else:
            logger.error("MQTT connection refused (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            logger.warning("MQTT disconnected unexpectedly (rc=%d) – reconnecting…", rc)

    def _on_message(self, client, userdata, msg):
        raw = msg.payload.decode("utf-8", errors="replace").strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Accept plain-text command strings like "stop" or "start_scene"
            payload = {"cmd": raw}

        logger.info("MQTT ← %s", payload)
        self._dispatch(payload)

    # ------------------------------------------------------------------
    # Command dispatcher
    # ------------------------------------------------------------------

    def _dispatch(self, payload: dict) -> None:
        cmd = str(payload.get("cmd", "")).lower().strip()

        if cmd == "start_scene":
            self._scene.start_scene(
                video=payload.get("video"),
                background=payload.get("background"),
                ambient=payload.get("ambient"),
            )
        elif cmd == "play_sound":
            filename = payload.get("file") or payload.get("sound")
            if filename:
                self._scene.play_sound(filename)
            else:
                logger.warning("play_sound: missing 'file' parameter")
        elif cmd == "play_ambient":
            filename = payload.get("file") or payload.get("sound")
            if filename:
                self._scene.play_ambient(filename)
            else:
                logger.warning("play_ambient: missing 'file' parameter")
        elif cmd == "play_audio":
            filename = payload.get("file") or payload.get("sound")
            mode = str(payload.get("mode", "once")).lower().strip()
            if not filename:
                logger.warning("play_audio: missing 'file' parameter")
            elif mode == "ambient":
                self._scene.play_ambient(filename)
            else:
                self._scene.play_sound(filename)
        elif cmd == "stop_sound":
            self._scene.stop_sound()
        elif cmd == "stop_ambient":
            self._scene.stop_ambient()
        elif cmd == "stop_audio":
            self._scene.stop_audio()
        elif cmd == "stop":
            self._scene.stop()
        elif cmd == "set_volume":
            self._scene._player.set_volume(payload.get("value", 80))
        else:
            logger.warning("Unknown command: %r", cmd)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def publish_status(self, status: dict) -> None:
        topic = self._cfg.get("topic_status", "escape/status")
        info = self._client.publish(topic, json.dumps(status))
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("Status publish failed (rc=%s): %s", info.rc, status)

    def start(self) -> None:
        """Connect and block in the MQTT loop (retries automatically)."""
        broker = self._cfg["broker"]
        port = self._cfg.get("port", 1883)
        keepalive = self._cfg.get("keepalive", 60)

        logger.info("Connecting to MQTT broker %s:%d", broker, port)
        self._client.connect(broker, port, keepalive)
        self._client.loop_forever(retry_first_connection=True)

    def stop(self) -> None:
        self._client.disconnect()
