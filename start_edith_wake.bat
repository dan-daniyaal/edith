@echo off
REM EDITH hands-free launcher - runs the wake-word listener.
REM Close this window (or press Ctrl+C in it) to stop EDITH.
title EDITH (hands-free)
cd /d "%~dp0"
python edith.py wake quiet
REM keep window open if it exits with an error, so you can see what happened
if errorlevel 1 pause
