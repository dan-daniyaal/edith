"""
EDITH control panel — local web server.

Serves the glass UI and exposes a small API to:
  - see live status + conversation
  - start / stop the hands-free wake listener
  - read & edit settings (voice, wake word, persona, sensitivity, toggles)
  - read & edit her project memory

Run:  python edith_ui/server.py   (opens http://127.0.0.1:5005 in your browser)
"""
import os
import sys
import json
import importlib
import threading
import webbrowser
import subprocess

from flask import Flask, request, jsonify, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
sys.path.insert(0, PROJECT)
import config  # noqa: E402

app = Flask(__name__, static_folder=HERE, static_url_path="")
_proc = None  # the EDITH wake subprocess this panel manages

VOICES = [
    {"id": "en-US-AvaNeural", "label": "Ava — US female (natural)"},
    {"id": "en-US-EmmaNeural", "label": "Emma — US female"},
    {"id": "en-US-JennyNeural", "label": "Jenny — US female"},
    {"id": "en-US-AriaNeural", "label": "Aria — US female"},
    {"id": "en-GB-SoniaNeural", "label": "Sonia — UK female"},
    {"id": "en-GB-LibbyNeural", "label": "Libby — UK female"},
    {"id": "en-US-GuyNeural", "label": "Guy — US male"},
    {"id": "en-GB-RyanNeural", "label": "Ryan — UK male"},
]
SETTING_FIELDS = [
    "EDGE_VOICE", "EDGE_RATE", "SPEECH_RATE", "WAKE_PHRASE", "WAKE_CONFIDENCE",
    "WAKE_SILENCE_MS", "WAKE_FOLLOWUP", "ENABLE_SCREEN", "ENABLE_WEATHER",
    "PERSONA_BASE",
]


def _running():
    return _proc is not None and _proc.poll() is None


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/api/status")
def status():
    state = {}
    try:
        with open(os.path.join(PROJECT, "edith_state.json"), encoding="utf-8") as f:
            state = json.load(f)
    except Exception:  # noqa: BLE001
        pass
    running = _running()
    return jsonify({
        "running": running,
        "activity": state.get("activity", "idle") if running else "offline",
        "history": state.get("history", []),
        "voice": state.get("voice", config.EDGE_VOICE),
        "wake_phrase": state.get("wake_phrase", config.WAKE_PHRASE),
    })


@app.route("/api/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        incoming = request.get_json(force=True) or {}
        try:
            with open(config.SETTINGS_FILE, encoding="utf-8") as f:
                current = json.load(f)
        except Exception:  # noqa: BLE001
            current = {}
        for k in SETTING_FIELDS:
            if k in incoming:
                current[k] = incoming[k]
        with open(config.SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return jsonify({"ok": True})

    importlib.reload(config)  # pick up any saved overrides
    return jsonify({
        "EDGE_VOICE": config.EDGE_VOICE,
        "EDGE_RATE": config.EDGE_RATE,
        "SPEECH_RATE": config.SPEECH_RATE,
        "WAKE_PHRASE": config.WAKE_PHRASE,
        "WAKE_CONFIDENCE": config.WAKE_CONFIDENCE,
        "WAKE_SILENCE_MS": config.WAKE_SILENCE_MS,
        "WAKE_FOLLOWUP": config.WAKE_FOLLOWUP,
        "ENABLE_SCREEN": config.ENABLE_SCREEN,
        "ENABLE_WEATHER": config.ENABLE_WEATHER,
        "PERSONA_BASE": config.PERSONA_BASE,
        "voices": VOICES,
    })


@app.route("/api/memory", methods=["GET", "POST"])
def memory():
    path = os.path.join(PROJECT, "memory.md")
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        with open(path, "w", encoding="utf-8") as f:
            f.write(data.get("text", ""))
        return jsonify({"ok": True})
    try:
        with open(path, encoding="utf-8") as f:
            return jsonify({"text": f.read()})
    except Exception:  # noqa: BLE001
        return jsonify({"text": ""})


@app.route("/api/start", methods=["POST"])
def start():
    global _proc
    if _running():
        return jsonify({"ok": True, "already": True})
    _proc = subprocess.Popen([sys.executable, "edith.py", "wake", "quiet"],
                             cwd=PROJECT)
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def stop():
    global _proc
    if _running():
        _proc.terminate()
        _proc = None
    try:
        with open(os.path.join(PROJECT, "edith_state.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"activity": "offline"}, f)
    except Exception:  # noqa: BLE001
        pass
    return jsonify({"ok": True})


if __name__ == "__main__":
    url = "http://127.0.0.1:5005"
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"EDITH control panel running at {url}  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=5005, debug=False)
