@echo off
REM EDITH gesture control - webcam hand tracking to control the mouse.
REM Point index finger = move cursor.  Pinch = click/drag.  Q or ESC = quit.
title EDITH Gesture Control
cd /d "%~dp0"
python gestures.py
if errorlevel 1 pause
