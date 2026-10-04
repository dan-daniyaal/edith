"""
EDITH — local voice assistant.

Pipeline each turn:
    microphone --> Whisper (ears) --> Claude Pro brain (Ollama fallback) --> SAPI voice (mouth)

Features:
- Persona + bio loaded from your Claude Project system prompt.
- On-demand screen vision: say "look at my screen".
- Two-layer memory:
    * short-term running conversation (re-sent each turn, capped, reset on "new chat")
    * long-term project memory.md (loaded every session; EDITH writes to it herself)

Press ENTER to start talking, ENTER again to stop. Say "quit"/"exit" or Ctrl+C to leave.

Run:  python edith.py
"""
import os
import re
import sys
import json
import time
import asyncio
import tempfile
import threading
import subprocess
from datetime import date, datetime

import numpy as np
import sounddevice as sd

import config

# Windows consoles default to cp1252, which can't print emoji — force UTF-8
# so status messages never crash EDITH.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if os.name == "nt":
        # tell the Windows console to render UTF-8 so em-dashes/emoji don't
        # show up as mojibake like "â€" (purely a display fix)
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
except Exception:  # noqa: BLE001
    pass


# Live status the control-panel UI polls (activity + recent conversation).
STATE_FILE = os.path.join(os.path.dirname(__file__), "edith_state.json")


def write_state(activity, history=None):
    """Publish current activity + recent turns for the UI. Best-effort."""
    try:
        data = {
            "activity": activity,            # idle | listening | thinking | speaking
            "voice": config.EDGE_VOICE,
            "wake_phrase": config.WAKE_PHRASE,
            "updated": time.time(),
        }
        if history is not None:
            data["history"] = history[-8:]
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
#  Ears: record from mic, transcribe with Whisper
# --------------------------------------------------------------------------- #
def record_until_enter():
    print("🎙️  Recording... press ENTER to stop.")
    frames = []
    stop = threading.Event()

    def wait_for_enter():
        input()
        stop.set()

    threading.Thread(target=wait_for_enter, daemon=True).start()

    def callback(indata, _frames, _time, status):
        if status:
            print(f"  (audio status: {status})", file=sys.stderr)
        frames.append(indata.copy())

    with sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1,
                        dtype="float32", callback=callback):
        while not stop.is_set():
            sd.sleep(100)

    if not frames:
        return np.zeros(1, dtype=np.float32)
    return np.concatenate(frames, axis=0).flatten()


_whisper_model = None


def transcribe(audio):
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print(f"🧠 Loading Whisper ({config.WHISPER_MODEL}) — first run downloads it...")
        _whisper_model = WhisperModel(config.WHISPER_MODEL, device="cpu",
                                      compute_type="int8")
    # vad_filter strips non-speech so Whisper can't hallucinate "urr urr" on noise
    segments, _info = _whisper_model.transcribe(
        audio, language="en", vad_filter=True, condition_on_previous_text=False,
    )
    return " ".join(seg.text for seg in segments).strip()


# --------------------------------------------------------------------------- #
#  Eyes: grab a screenshot only when asked
# --------------------------------------------------------------------------- #
def wants_screen(text):
    if not config.ENABLE_SCREEN:
        return False
    low = text.lower()
    return any(trigger in low for trigger in config.SCREEN_TRIGGERS)


def is_new_chat(text):
    low = text.lower().strip(" .!?")
    return any(trigger in low for trigger in config.NEW_CHAT_TRIGGERS)


def capture_screen():
    try:
        import mss
        import mss.tools
        path = os.path.join(tempfile.gettempdir(), "edith_screen.png")
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # primary display
            mss.tools.to_png(shot.rgb, shot.size, output=path)
        return path
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Couldn't capture screen ({exc}).")
        return None


# --------------------------------------------------------------------------- #
#  Long-term memory (memory.md)
# --------------------------------------------------------------------------- #
def load_memory():
    try:
        with open(config.MEMORY_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def append_memory(fact):
    fact = fact.strip()
    if not fact:
        return
    header_needed = not os.path.exists(config.MEMORY_FILE)
    with open(config.MEMORY_FILE, "a", encoding="utf-8") as fh:
        if header_needed:
            fh.write("# EDITH — Project Memory\n\n")
        fh.write(f"- ({date.today().isoformat()}) {fact}\n")
    print(f"💾 Saved to memory: {fact}")


_MEMORY_TAG = re.compile(r"<<MEMORY:\s*(.*?)>>", re.DOTALL)


def extract_memories(reply):
    """Pull out <<MEMORY: ...>> tags; return (spoken_text, [facts])."""
    facts = [m.strip() for m in _MEMORY_TAG.findall(reply)]
    spoken = _MEMORY_TAG.sub("", reply).strip()
    return spoken, facts


# --------------------------------------------------------------------------- #
#  Brain: Claude Pro CLI, with local Ollama as fallback
# --------------------------------------------------------------------------- #
def _build_system():
    mem = load_memory()
    system = config.EDITH_PERSONA
    now = datetime.now().astimezone()
    system += (f"\n\n=== RIGHT NOW ===\nCurrent local date & time: "
               f"{now:%A, %B %d, %Y, %I:%M %p} ({now.tzname()}). "
               f"You DO know the current time — it's stated here, so just answer it.")
    if mem:
        system += "\n\n=== YOUR PROJECT MEMORY (durable facts you saved) ===\n" + mem
    return system


def _format_history(history):
    recent = history[-config.MAX_HISTORY_TURNS:]
    if not recent:
        return ""
    lines = ["[Earlier in this conversation:]"]
    for turn in recent:
        lines.append(f"Dan: {turn['user']}")
        lines.append(f"EDITH: {turn['edith']}")
    return "\n".join(lines) + "\n\n"


def wants_weather(text):
    if not config.ENABLE_WEATHER:
        return False
    low = text.lower()
    return any(t in low for t in config.WEATHER_TRIGGERS)


def fetch_weather():
    """Current conditions from wttr.in (free, no key). Returns a string or None."""
    import urllib.request
    import urllib.parse
    loc = urllib.parse.quote(config.WEATHER_LOCATION)
    fmt = urllib.parse.quote("%l: %C, %t (feels %f), wind %w, humidity %h")
    url = f"https://wttr.in/{loc}?format={fmt}"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            return resp.read().decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Weather lookup failed ({exc}).")
        return None


def think(user_text, history, screenshot_path=None, weather=None):
    """Ask Claude (Pro, no API key). Fall back to local Ollama on failure."""
    system = _build_system()
    prompt = _format_history(history) + f"Dan: {user_text}"
    if weather:
        prompt += (f"\n\n[Live weather right now: {weather}. "
                   f"Use this to answer his weather question naturally.]")
    # Always allow the read-only tool whitelist (Gmail/Calendar/Drive reads +
    # local file Read). Write tools are never whitelisted, so she can't send or
    # delete anything even if misheard.
    cmd = [config.CLAUDE_BIN, "-p", prompt, "--append-system-prompt", system,
           "--allowedTools", config.ALLOWED_TOOLS_ARG]
    if screenshot_path:
        prompt += (
            f"\n\n[A screenshot of Dan's current screen is saved at: "
            f"{screenshot_path}. Use the Read tool to view it, then answer.]"
        )
        cmd[2] = prompt

    try:
        result = subprocess.run(
            cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace",  # Claude outputs UTF-8, not cp1252
            timeout=config.BRAIN_TIMEOUT,
        )
        reply = result.stdout.strip()
        if result.returncode == 0 and reply:
            return reply
        print(f"⚠️  Claude unavailable ({result.stderr.strip()[:120]}) — using Ollama.")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Claude error ({exc}) — using Ollama.")

    if screenshot_path:
        return "I can't see your screen right now, Dan — my cloud eyes are offline."
    return think_ollama(user_text, system, history)


def think_ollama(user_text, system, history):
    try:
        prompt = f"{system}\n\n{_format_history(history)}Dan: {user_text}\nEDITH:"
        result = subprocess.run(
            [config.OLLAMA_BIN, "run", config.OLLAMA_MODEL, prompt],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=config.BRAIN_TIMEOUT,
        )
        return result.stdout.strip() or "I'm sorry Dan, I couldn't reach either brain."
    except Exception as exc:  # noqa: BLE001
        return f"I'm sorry Dan, both brains are offline. ({exc})"


# --------------------------------------------------------------------------- #
#  Mouth: neural edge-tts voice (Aria), with offline SAPI fallback
# --------------------------------------------------------------------------- #
def _clean_for_speech(text):
    text = re.sub(r"[*_`#>]+", "", text)          # strip markdown
    # normalize fancy punctuation to speech-friendly forms
    for bad, good in {
        "—": ", ", "–": ", ", "―": ", ",   # em/en/horizontal dash
        "…": ". ",                                    # ellipsis
        "“": "", "”": "",                        # curly double quotes
        "‘": "'", "’": "'",                       # curly single quotes
        "•": " ", "·": " ", "−": "-",        # bullets, minus
    }.items():
        text = text.replace(bad, good)
    # drop anything left that isn't letters/digits/space/basic punctuation
    text = re.sub(r"[^\w\s.,!?;:'\"-]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --- Primary voice: edge-tts neural (natural, free, needs internet) ---------
_pygame_ready = False


def _ensure_pygame():
    global _pygame_ready
    if not _pygame_ready:
        import pygame
        pygame.mixer.init()
        _pygame_ready = True


async def _edge_synth(text, path):
    import edge_tts
    await edge_tts.Communicate(
        text, config.EDGE_VOICE, rate=config.EDGE_RATE, pitch=config.EDGE_PITCH
    ).save(path)


def _speak_edge(text):
    import pygame
    _ensure_pygame()
    path = os.path.join(tempfile.gettempdir(), "edith_say.mp3")
    asyncio.run(_edge_synth(text, path))
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


# --- Offline fallback: Windows SAPI voice -----------------------------------
_sapi_engine = None


def _speak_sapi(text):
    global _sapi_engine
    if _sapi_engine is None:
        import pyttsx3
        eng = pyttsx3.init()
        eng.setProperty("rate", config.SPEECH_RATE)
        voices = eng.getProperty("voices")
        for pref in config.VOICE_PREFERENCES:
            match = next((v.id for v in voices
                          if pref in (v.name or "").lower()
                          or pref in (v.id or "").lower()), None)
            if match:
                eng.setProperty("voice", match)
                break
        _sapi_engine = eng
    _sapi_engine.say(text)
    _sapi_engine.runAndWait()


def speak(text):
    clean = _clean_for_speech(text)
    if not clean:
        return
    try:
        _speak_edge(clean)
    except Exception as exc:  # noqa: BLE001 — fall back to offline voice
        print(f"⚠️  Neural voice failed ({exc}) — using system voice.")
        _speak_sapi(clean)


# --------------------------------------------------------------------------- #
#  Shared command handling (used by both ENTER mode and wake mode)
# --------------------------------------------------------------------------- #
def handle_command(user_text, history):
    """Process one transcribed command. Returns False if EDITH should quit."""
    low = user_text.lower().strip(" .!?")
    if low in {"quit", "exit", "goodbye", "stop"}:
        speak("Goodbye, Dan.")
        return False

    if is_new_chat(user_text):
        history.clear()
        print("🧹 Conversation cleared (project memory kept).")
        speak("Fresh start, Boss. Clean slate.")
        return True

    shot = None
    if wants_screen(user_text):
        print("👁️  Capturing your screen...")
        shot = capture_screen()

    weather = None
    if wants_weather(user_text):
        print("🌦️  Checking weather...")
        weather = fetch_weather()

    write_state("thinking", history)
    print("🤔 Thinking...")
    raw = think(user_text, history, screenshot_path=shot, weather=weather)
    spoken, facts = extract_memories(raw)
    for fact in facts:
        append_memory(fact)
    spoken = _clean_for_speech(spoken)  # ASCII-safe: clean for BOTH screen + voice
    print(f"🤖 EDITH: {spoken}")
    history.append({"user": user_text, "edith": spoken})
    write_state("speaking", history)
    speak(spoken)
    return True


# --------------------------------------------------------------------------- #
#  ENTER mode (push-to-talk)
# --------------------------------------------------------------------------- #
def main():
    print("=" * 60)
    print("  EDITH online (push-to-talk).  Brain:", config.CLAUDE_BIN)
    print("  ENTER to talk, ENTER again to stop.  Ctrl+C to quit.")
    print('  "look at my screen" = vision   |   "new topic" = fresh chat')
    print("=" * 60)

    history = []
    speak("EDITH online. What do you need, Boss?")

    while True:
        try:
            input("\n▶  Press ENTER to talk...")
            audio = record_until_enter()
            print("📝 Transcribing...")
            user_text = transcribe(audio)
            if not user_text:
                print("   (heard nothing — try again)")
                continue
            print(f"🗣️  You: {user_text}")
            if not handle_command(user_text, history):
                break
        except KeyboardInterrupt:
            print("\nShutting down. Goodbye, Dan.")
            break


# --------------------------------------------------------------------------- #
#  Wake mode ("Hey EDITH", hands-free) — openWakeWord, low power, no signup
# --------------------------------------------------------------------------- #
def _listen_utterance(sr=16000):
    """Capture one spoken phrase (float32) — waits for speech, ends on silence.

    Returns None on timeout or if too little actual speech was heard (noise).
    """
    block = int(0.05 * sr)  # 50 ms blocks
    silence_needed = max(1, int((config.WAKE_SILENCE_MS / 1000) / 0.05))
    min_voiced = max(1, int((config.WAKE_MIN_SPEECH_MS / 1000) / 0.05))
    max_blocks = int(config.WAKE_MAX_SECONDS / 0.05)
    collected, started, silence, waited, voiced = [], False, 0, 0.0, 0
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32",
                        blocksize=block) as stream:
        while True:
            data, _ = stream.read(block)
            data = data.reshape(-1)
            rms = float(np.sqrt(np.mean(data ** 2)))
            if not started:
                if rms > config.WAKE_VAD_THRESHOLD:
                    started = True
                    voiced += 1
                    collected.append(data.copy())
                else:
                    waited += 0.05
                    if waited > config.WAKE_COMMAND_TIMEOUT:
                        return None
            else:
                collected.append(data.copy())
                if rms > config.WAKE_VAD_THRESHOLD:
                    silence = 0
                    voiced += 1
                else:
                    silence += 1
                    if silence >= silence_needed:
                        break
                if len(collected) >= max_blocks:
                    break
    if voiced < min_voiced:          # too little real speech → treat as noise
        return None
    return np.concatenate(collected) if collected else None


def _wait_for_wake(vmodel):
    """Block (offline, local) until the wake phrase is heard. Returns on match.

    Only acts on FINALIZED results (not live partials) and requires the full
    phrase "hey <word>", which keeps false triggers low.
    """
    from vosk import KaldiRecognizer
    rec = KaldiRecognizer(vmodel, 16000, f'["hey {config.WAKE_PHRASE}", "[unk]"]')
    rec.SetWords(True)  # per-word confidence so we can reject weak matches
    phrase = f"hey {config.WAKE_PHRASE}"
    block = 4000  # ~0.25 s at 16 kHz
    with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                        blocksize=block) as stream:
        while True:
            data, _ = stream.read(block)
            buf = data.reshape(-1).tobytes()
            if rec.AcceptWaveform(buf):  # only when an utterance finalizes
                res = json.loads(rec.Result())
                text = res.get("text", "").lower()
                words = res.get("result", [])
                conf = min((w.get("conf", 1.0) for w in words), default=0.0)
                # require the full "hey <word>" phrase AND decent confidence
                if phrase in text and conf >= config.WAKE_CONFIDENCE:
                    return


def run_wake(greet=True):
    if not config.VOSK_MODEL_PATH:
        print("Vosk wake model not found in this folder.")
        print("See README.md → Wake word setup. Falling back to push-to-talk.\n")
        return main()

    from vosk import Model as VoskModel, SetLogLevel
    SetLogLevel(-1)  # silence Vosk's verbose logging
    vmodel = VoskModel(config.VOSK_MODEL_PATH)
    history = []
    print("=" * 60)
    print('  EDITH online (hands-free).  Say "Hey EDITH" to wake her.')
    print("  Listening is 100% offline.  Ctrl+C to quit.")
    print("=" * 60)
    print("  (warming up speech engine...)")
    transcribe(np.zeros(8000, dtype=np.float32))  # preload Whisper now, not mid-chat
    if greet:  # silenced on auto-start so she doesn't announce in public
        speak("EDITH standing by. Just say my name, Boss.")

    try:
        while True:
            write_state("listening", history)
            _wait_for_wake(vmodel)
            print("🔔 Heard you.")
            write_state("thinking", history)
            speak("Yes, Boss?")
            # Conversation: after waking, keep handling follow-ups without
            # re-saying "Hey EDITH" — until you go quiet, then back to sleep.
            while True:
                audio = _listen_utterance()
                if audio is None:
                    break  # silence → return to listening for "Hey EDITH"
                print("📝 Transcribing...")
                user_text = transcribe(audio)
                if not user_text:
                    break
                print(f"🗣️  You: {user_text}")
                if not handle_command(user_text, history):
                    return  # quit command
                if not config.WAKE_FOLLOWUP:
                    break  # one-shot mode: require wake word each time
                print('   (listening for a follow-up — or say "Hey EDITH" later)')
    except KeyboardInterrupt:
        print("\nShutting down. Goodbye, Dan.")


if __name__ == "__main__":
    args = [a.lower() for a in sys.argv[1:]]
    if args and args[0] in {"wake", "--wake", "-w"}:
        # "quiet" (used by auto-start) skips the spoken boot greeting
        run_wake(greet=not ("quiet" in args or "-q" in args))
    else:
        main()
