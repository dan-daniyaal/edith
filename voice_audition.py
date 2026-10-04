"""
Audition neural voices for EDITH (free, via edge-tts).
Plays each candidate so you can pick. Run:  python voice_audition.py
Then tell which number you want, and it becomes EDITH's voice.
"""
import os
import time
import asyncio
import tempfile

import edge_tts
import pygame

# Curated candidates: mix of US/UK, female/male. Add/remove freely.
VOICES = [
    ("en-US-AriaNeural",     "American female — Aria, warm and confident"),
    ("en-US-JennyNeural",    "American female — Jenny, friendly"),
    ("en-US-MichelleNeural", "American female — Michelle, smooth"),
    ("en-GB-SoniaNeural",    "British female — Sonia, crisp and composed"),
    ("en-GB-LibbyNeural",    "British female — Libby, younger"),
    ("en-US-GuyNeural",      "American male — Guy, steady"),
    ("en-GB-RyanNeural",     "British male — Ryan, dry"),
]


async def _synth(voice, text, path):
    await edge_tts.Communicate(text, voice).save(path)


def _play(path):
    pygame.mixer.music.load(path)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.1)
    pygame.mixer.music.unload()


def main():
    pygame.mixer.init()
    print("Auditioning EDITH voices — listen, then tell Dan the number you like.\n")
    for i, (voice, desc) in enumerate(VOICES, 1):
        line = (f"Voice number {i}. {desc}. "
                f"I am EDITH, your tactical AI assistant. "
                f"If you like this one, tell Dan to pick number {i}.")
        path = os.path.join(tempfile.gettempdir(), f"edith_aud_{i}.mp3")
        asyncio.run(_synth(voice, line, path))
        print(f"  [{i}] {voice}  —  {desc}")
        _play(path)
        time.sleep(0.4)
    print("\nDone. Tell Dan which number sounded best.")


if __name__ == "__main__":
    main()
