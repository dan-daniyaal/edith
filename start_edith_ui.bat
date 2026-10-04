@echo off
REM EDITH control panel - opens the glass UI in your browser.
title EDITH Control Panel
cd /d "%~dp0"
python edith_ui\server.py
if errorlevel 1 pause
