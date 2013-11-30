@echo off
set PYTHONPATH=%~dp0
REM i18n support doesn't work on Windows, default to English.
set LANG=en
c:\python27\python.exe scripts\mailpile %*
