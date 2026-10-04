"""
EDITH local voice agent — configuration.
Edit values here; no code changes needed for normal tweaks.
"""
import os
import re
import shutil

# ---- Brain ----------------------------------------------------------------
# Primary brain: Claude Code CLI (headless), powered by your Claude Pro login.
# No API key, no per-token cost. Falls back to local Ollama if Claude fails.
CLAUDE_BIN = os.path.expandvars(r"%USERPROFILE%\.local\bin\claude.exe")
if not os.path.exists(CLAUDE_BIN):
    CLAUDE_BIN = shutil.which("claude") or CLAUDE_BIN

# Fallback brain: local Ollama model (used only if Claude is unavailable /
# rate-limited). You already have qwen2.5 pulled.
OLLAMA_BIN = os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe")
if not os.path.exists(OLLAMA_BIN):
    OLLAMA_BIN = shutil.which("ollama") or OLLAMA_BIN
OLLAMA_MODEL = "qwen2.5"

BRAIN_TIMEOUT = 120  # seconds before a brain call is abandoned

# ---- Ears (speech-to-text) -----------------------------------------------
WHISPER_MODEL = "base.en"   # tiny.en / base.en / small.en / medium.en
SAMPLE_RATE = 16000         # Whisper expects 16 kHz mono

# ---- Mouth (text-to-speech) ----------------------------------------------
# Primary: edge-tts neural voice (natural, free, no key — needs internet).
# Browse more: run  python -m edge_tts --list-voices
EDGE_VOICE = "en-US-AvaNeural"    # Ava — newest-gen, natural American female
EDGE_RATE = "+0%"                 # speed, e.g. "+10%" faster, "-10%" slower
EDGE_PITCH = "+0Hz"               # pitch, e.g. "+20Hz" higher, "-20Hz" lower

# Offline fallback: Windows SAPI voice, used only if edge-tts can't reach the net.
VOICE_PREFERENCES = ["zira", "hazel", "en-us", "en-gb"]
SPEECH_RATE = 175  # words per minute (SAPI fallback only)

# ---- Screen vision (on-demand) -------------------------------------------
# Saying one of these grabs a screenshot for that one request (saves tokens).
SCREEN_TRIGGERS = [
    "look at my screen", "look at the screen", "what's on my screen",
    "whats on my screen", "see my screen", "what am i looking at",
    "look at this", "read my screen",
]

# ---- Conversation memory --------------------------------------------------
# Short-term: the running conversation is held in RAM and re-sent each turn,
# capped to the last N exchanges so context never bloats. Saying any NEW_CHAT
# phrase clears it (fresh reasoning) WITHOUT wiping the long-term memory file.
MAX_HISTORY_TURNS = 12
NEW_CHAT_TRIGGERS = [
    "new chat", "new topic", "fresh start", "start over",
    "clear context", "new conversation", "forget this conversation",
]

# Long-term: a compact "project memory" file loaded into EVERY session
# (including fresh ones). EDITH appends to it herself when you ask her to
# remember something durable.
MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.md")

# Local knowledge base (drop degree audit, resume, notes here).
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")

# ---- Weather (free, no API key, via wttr.in) -----------------------------
# When a command mentions weather, EDITH fetches current conditions and answers.
WEATHER_TRIGGERS = [
    "weather", "temperature", "how hot", "how cold", "raining", "rain today",
    "forecast", "humid", "outside right now",
]
WEATHER_LOCATION = ""  # blank = auto-detect by IP; or set e.g. "London"

# ---- Tools (Phase 1: READ-ONLY) ------------------------------------------
# EDITH's brain (Claude CLI) already has your connectors wired. We allow ONLY
# read/search/get tools so a misheard command can never send or delete anything.
# Write tools (send email, create/delete events, drafts) are deliberately OFF
# until the draft-and-confirm flow is added in Phase 2.
READ_TOOLS = [
    "Read",  # local files (and screenshots)
    # Google Calendar — reads only
    "mcp__claude_ai_Google_Calendar__list_calendars",
    "mcp__claude_ai_Google_Calendar__list_events",
    "mcp__claude_ai_Google_Calendar__get_event",
    "mcp__claude_ai_Google_Calendar__suggest_time",
    # Gmail — reads only
    "mcp__claude_ai_Gmail__search_threads",
    "mcp__claude_ai_Gmail__get_thread",
    "mcp__claude_ai_Gmail__list_drafts",
    "mcp__claude_ai_Gmail__list_labels",
    # Google Drive — reads only
    "mcp__claude_ai_Google_Drive__search_files",
    "mcp__claude_ai_Google_Drive__list_recent_files",
    "mcp__claude_ai_Google_Drive__read_file_content",
    "mcp__claude_ai_Google_Drive__get_file_metadata",
]
ALLOWED_TOOLS_ARG = ",".join(READ_TOOLS)

# ---- Wake word ("Hey EDITH" via Vosk) ------------------------------------
# Run hands-free with:  python edith.py wake
# Fully OFFLINE phrase spotting — no training, no signup, no cloud. The idle
# listening never leaves your laptop. The Vosk model folder is auto-detected
# (downloaded into this folder during setup).
import glob as _glob

_vosk = _glob.glob(os.path.join(os.path.dirname(__file__), "vosk-model*"))
VOSK_MODEL_PATH = next((p for p in _vosk if os.path.isdir(p)), "")
WAKE_PHRASE = "edith"       # the word Vosk listens for to wake her

WAKE_CONFIDENCE = 0.6       # min recognizer confidence to accept "hey edith"
WAKE_VAD_THRESHOLD = 0.015  # speech-energy gate for command capture (float RMS)
WAKE_MIN_SPEECH_MS = 350    # ignore captures shorter than this (noise, not speech)
WAKE_COMMAND_TIMEOUT = 6    # secs to wait for you to speak after "Yes, Boss?"
WAKE_MAX_SECONDS = 12       # max length of a single spoken command
WAKE_SILENCE_MS = 1000      # trailing silence that ends a command
WAKE_FOLLOWUP = True        # after answering, listen for a follow-up w/o re-waking

# ---- EDITH persona --------------------------------------------------------
# Optional private persona file (git-ignored). If missing, a built-in
# default persona is used instead.
_SYSTEM_PROMPT_FILE = os.path.join(os.path.dirname(__file__), "EDITH_SYSTEM_PROMPT.md")

_VOICE_TTS_RULES = """
=== LOCAL VOICE MODE (added on top of the above) ===
Your replies are spoken aloud by a text-to-speech engine and you are running \
locally on Dan's laptop, NOT in the cloud Project.
- Output PLAIN SPOKEN TEXT only: no markdown, no asterisks, no bullet symbols, \
no code blocks, no emoji, no raw URLs. Write numbers and times as you'd say them.
- Keep it tight — usually 1 to 3 sentences unless he clearly wants detail.
- TOOLS: In this local mode you have LIVE READ access to Gmail, Google Calendar, \
and Google Drive — use them to answer ("what's on my calendar", "any urgent \
emails", "find my resume in Drive"). You CANNOT yet send email, create/change/\
delete calendar events, or write files locally — those write actions are not \
wired in yet. If Dan asks you to send or change something, say in one line that \
local write mode isn't enabled yet and offer to do it once it is (or that he can \
do it in the cloud EDITH Project).
- If a screenshot path is provided in the message, use the Read tool to view it, \
then answer about what's actually on his screen.

=== PROJECT MEMORY ===
You have a persistent project memory of durable facts about Dan that survive across \
fresh sessions. It is shown to you each session under "YOUR PROJECT MEMORY".
- When Dan asks you to remember something durable (e.g. "remember I'm waiting \
on a reply about that interview", "note my exam is next Friday"), OR something is \
clearly important to retain, append ONE line at the very END of your reply in this \
EXACT format:
<<MEMORY: the concise fact, dated/phrased so future-you understands it>>
That tagged line is saved to your memory file and is stripped out before your words \
are spoken, so speak your normal reply first, then add the tag. Only emit it when it \
genuinely matters. One tight line per memory.
"""


def _load_persona():
    try:
        with open(_SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as fh:
            raw = fh.read()
        match = re.search(r"```text\s*(.*?)```", raw, re.DOTALL)
        return (match.group(1) if match else raw).strip()
    except OSError:
        return (
            "You are EDITH, Dan's sharp, sarcastic, hyper-competent and loyal "
            "personal AI assistant, modeled on the EDITH AI from Spider-Man: "
            "Far From Home. Be direct and concise."
        )


PERSONA_BASE = _load_persona()              # editable in the UI
EDITH_PERSONA = PERSONA_BASE + "\n" + _VOICE_TTS_RULES

# ---- Feature toggles (editable via the control-panel UI) -----------------
ENABLE_SCREEN = True       # "look at my screen" vision
ENABLE_WEATHER = True      # weather lookups

# ---- Settings overlay (written by the control-panel UI) ------------------
# settings.json overrides the tunable values above so the UI can change EDITH
# without editing code. She re-reads it on (re)start.
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")
_OVERRIDABLE = (
    "EDGE_VOICE", "EDGE_RATE", "SPEECH_RATE", "WAKE_PHRASE", "WAKE_CONFIDENCE",
    "WAKE_SILENCE_MS", "WAKE_FOLLOWUP", "ENABLE_SCREEN", "ENABLE_WEATHER",
)


def _apply_settings_overrides():
    import json as _json
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as _fh:
            data = _json.load(_fh)
    except (OSError, ValueError):
        return
    g = globals()
    for key in _OVERRIDABLE:
        if key in data and data[key] not in (None, ""):
            g[key] = data[key]
    persona = data.get("PERSONA_BASE")
    if persona and persona.strip():
        g["PERSONA_BASE"] = persona.strip()
        g["EDITH_PERSONA"] = persona.strip() + "\n" + _VOICE_TTS_RULES


_apply_settings_overrides()
