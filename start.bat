@echo off
cd /d "%~dp0"
py -3 -m jobwatcher.app ui
pause
