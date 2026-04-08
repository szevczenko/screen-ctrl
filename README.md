# screen-ctrl

Python media player controlled by MQTT (Node-RED friendly).

## Requirements

System packages:
- mosquitto
- mosquitto-clients
- mpv
- libmvp1
- python3
- python3-pip
- python3-venv

Python packages:
- paho-mqtt
- PyYAML

## Install

Option A: automatic installer (recommended on Raspberry Pi)

~~~bash
cd screen-ctrl
sudo bash install.sh
~~~

This installs system dependencies, creates Python virtual environment, installs Python deps, and prepares systemd service.

Option B: manual install

~~~bash
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients mpv python3 python3-pip python3-venv

cd screen-ctrl
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
~~~

## Fast Run (local)

1. Start broker:

~~~bash
cd screen-ctrl
mosquitto -c mosquitto.conf -v
~~~

2. Start app (new terminal):

~~~bash
cd screen-ctrl
python3 main.py --config config.yml
~~~

3. Subscribe to status events (new terminal):

~~~bash
mosquitto_sub -h localhost -t "escape/status" -v
~~~

4. Send commands (new terminal):

~~~bash
# start scene
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"start_scene"}'

# one-shot mp3
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"play_sound","file":"scare.mp3"}'

# ambient loop mp3
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"play_ambient","file":"ambient.mp3"}'

# interrupt one-shot sounds
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_sound"}'

# interrupt ambient loop
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_ambient"}'

# stop all audio only
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop_audio"}'

# stop everything
mosquitto_pub -h localhost -t "escape/control" -m '{"cmd":"stop"}'
~~~

## Service run (Raspberry Pi)

~~~bash
sudo systemctl enable screen-ctrl
sudo systemctl start screen-ctrl
journalctl -fu screen-ctrl
~~~

## Notes

- If you see "No such file or directory: mpv", check installation and PATH.
- Make sure media files exist in paths configured in config.yml.
- Full protocol details are documented in docs/SCREEN_CTRL_GUIDE.md.
