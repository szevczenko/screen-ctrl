# screen-ctrl Guide

## 1. What This App Does

screen-ctrl is a Python media runtime controlled by MQTT (typically from Node-RED).
It runs on Raspberry Pi (or Linux) and controls:

- video playback (mpv)
- background image display (mpv)
- ambient audio loop (mpv)
- one-shot sound effects (mpv)

Main scene flow:

1. Receive `start_scene`
2. Play video
3. When video ends naturally, switch to image
4. Start ambient loop
5. At any time, allow one-shot sound effect

## 2. Architecture

Sensors / puzzle logic -> Node-RED -> MQTT -> screen-ctrl (Python) -> mpv -> screen + speaker

### Core modules

- `main.py`: startup, logging, wiring of events to MQTT status
- `app/mqtt_client.py`: receives control commands and dispatches actions
- `app/scene.py`: scene orchestration logic
- `app/player.py`: low-level mpv process management
- `config.yml`: runtime configuration (broker, paths, defaults)

## 3. Topics and Message Frames

Default topics (from `config.yml`):

- control topic (incoming): `escape/control`
- status topic (outgoing): `escape/status`

### 3.1 Incoming control frames (received by screen-ctrl)

All commands are JSON frames published to control topic.

#### Start default scene

```json
{"cmd":"start_scene"}
```

#### Start scene with explicit media

```json
{"cmd":"start_scene","video":"intro.mp4","background":"tlo.png","ambient":"ambient.mp3"}
```

#### Play one-shot sound once

```json
{"cmd":"play_sound","file":"scare.mp3"}
```

#### Start/restart ambient loop

```json
{"cmd":"play_ambient","file":"ambient.mp3"}
```

#### Generic audio command (mode=once|ambient)

```json
{"cmd":"play_audio","mode":"once","file":"scare.mp3"}
{"cmd":"play_audio","mode":"ambient","file":"ambient.mp3"}
```

#### Interrupt one-shot sounds only

```json
{"cmd":"stop_sound"}
```

#### Interrupt ambient only

```json
{"cmd":"stop_ambient"}
```

#### Interrupt all audio (keep video/image)

```json
{"cmd":"stop_audio"}
```

#### Set volume (0-100)

```json
{"cmd":"set_volume","value":70}
```

#### Stop everything

```json
{"cmd":"stop"}
```

### 3.2 Outgoing status frames (sent by screen-ctrl)

Published to status topic with metadata:

- `ts`: UTC timestamp (ISO format)
- `source`: `screen-ctrl`
- event-specific fields

Examples:

#### Video started

```json
{"ts":"2026-04-08T11:00:00+00:00","source":"screen-ctrl","event":"video_started","file":"intro.mp4"}
```

#### Video finished

```json
{"ts":"2026-04-08T11:00:05+00:00","source":"screen-ctrl","event":"video_finished","file":"intro.mp4","returncode":0,"cancelled":false}
```

#### One-shot sound started / finished

```json
{"ts":"2026-04-08T11:00:10+00:00","source":"screen-ctrl","event":"sound_started","file":"scare.mp3"}
{"ts":"2026-04-08T11:00:11+00:00","source":"screen-ctrl","event":"sound_finished","file":"scare.mp3","returncode":0}
```

#### Ambient started / stopped

```json
{"ts":"2026-04-08T11:00:06+00:00","source":"screen-ctrl","event":"ambient_started","file":"ambient.mp3"}
{"ts":"2026-04-08T11:01:00+00:00","source":"screen-ctrl","event":"ambient_stopped"}
```

#### Sound interrupted

```json
{"ts":"2026-04-08T11:01:02+00:00","source":"screen-ctrl","event":"sound_stopped"}
```

## 4. Media Directory Layout

Recommended structure:

```text
screen-ctrl/
  media/
    videos/
    images/
    audio/
```

`config.yml` maps these directories via:

- `media.base_path`
- `media.videos_dir`
- `media.images_dir`
- `media.audio_dir`

## 5. How to Run

### 5.1 Start broker (local test)

```bash
mosquitto -c mosquitto.conf -v
```

### 5.2 Start app

```bash
python3 main.py --config config.yml
```

### 5.3 Send test command

```bash
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"start_scene"}'
```

### 5.4 Observe status events

```bash
mosquitto_sub -h localhost -t "escape/status" -v
```

## 6. Node-RED Usage Pattern

Typical flow in Node-RED:

1. Trigger node (button/sensor/logic)
2. Function node builds JSON frame
3. MQTT Out publishes to control topic
4. Optional MQTT In listens on status topic for acknowledgements and timing

## 7. Operational Notes

- `stop` cancels the scene and terminates all mpv processes.
- `stop_audio` is safer when you only want silence without touching visuals.
- Ambient is single-instance: starting new ambient replaces previous ambient.
- One-shot sounds can overlap and are independently interruptible via `stop_sound`.
- If no media appears, verify paths in `config.yml` and check app logs.

## 8. Quick Troubleshooting

- `No such file or directory: mpv`:
  - mpv not in PATH used by process
- No playback after command:
  - wrong filename
  - wrong media path mapping in config
  - missing MQTT connection
- No status events:
  - verify `topic_status`
  - subscribe to correct broker/topic

## 9. Minimal Command Cheat Sheet

```bash
# Start scene
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"start_scene"}'

# Play one-shot
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"play_sound","file":"scare.mp3"}'

# Start ambient loop
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"play_ambient","file":"ambient.mp3"}'

# Stop only one-shot sounds
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_sound"}'

# Stop only ambient
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_ambient"}'

# Stop all audio
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_audio"}'

# Stop everything
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop"}'
```