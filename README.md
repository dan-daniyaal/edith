# EDITH — Local Voice Assistant

A fully local, voice-driven personal assistant inspired by EDITH (Spider-Man: Far From Home).
You talk to it, it thinks with **Claude (your Pro plan — no API key)**, and it talks back.

```
microphone → Whisper (ears) → Claude Pro brain → SAPI voice (mouth)
                                   ↓ (if Claude is down)
                              local Ollama qwen2.5
```

Everything runs on your machine. The only "cost" is your existing Claude Pro plan.

## What's already set up
- ✅ Claude Code CLI installed + logged in with Pro (`claude -p` works)
- ✅ Python 3.12 and Ollama present
- ✅ `qwen2.5` available as fallback brain

## One-time setup
Install the Python voice dependencies:

```powershell
cd "Project Edith"
pip install -r requirements.txt
```

The first time you run EDITH, Whisper downloads its `base.en` model (~140 MB) automatically.

## Run it
```powershell
python edith.py
```

- Press **ENTER** to start talking, **ENTER** again to stop.
- Say **"quit"** / **"exit"**, or press **Ctrl+C**, to leave.

## Tweaking (all in `config.py`)
- **Voice**: edit `VOICE_PREFERENCES`. Want a better British voice? Add the
  "Microsoft Hazel" voice via Windows → Settings → Time & Language → Speech.
- **Persona**: edit `EDITH_PERSONA`.
- **Accuracy vs. speed**: change `WHISPER_MODEL` (`tiny.en` faster, `small.en` sharper).
- **Fallback model**: change `OLLAMA_MODEL`.

## Wake word — "Hey EDITH" (hands-free mode)
Uses **Vosk** — free, fully **offline** phrase spotting. No training, no signup,
no cloud; the idle listening never leaves your laptop. The model folder
(`vosk-model-small-en-us-0.15`) lives in this folder and is auto-detected.

If the model folder is ever missing, re-download it (~40 MB):
https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
→ unzip into this folder.

Run hands-free:
```powershell
python edith.py wake
```
Say **"Hey EDITH"** → she replies "Yes, Boss?" → speak your command → she
auto-stops on silence and answers. Plain `python edith.py` is still push-to-talk.

Tuning (in `config.py`): `WAKE_PHRASE` (the trigger word), `WAKE_VAD_THRESHOLD`
(lower if it ignores quiet speech), `WAKE_COMMAND_TIMEOUT`, `WAKE_SILENCE_MS`,
`WAKE_MAX_SECONDS`.

## Roadmap (next upgrades)
- Phase 2 tools: send email / create events with a draft-and-confirm voice gate
- Global hotkey + auto-start on login
- Better TTS voice via Piper for an even closer EDITH tone
