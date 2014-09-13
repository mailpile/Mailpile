@echo off
set PATH=%PATH%;GnuPG\;OpenSSL\;
set PYTHONPATH=%~dp0;%~dp0\GnuPG\;%~dp0\OpenSSL\;
if exist python27\python.exe (
  set PYTHONBIN=python27\python.exe
) else if exist c:\python27\python.exe (
  set PYTHONBIN=c:\python27\python.exe
) else (
  set PYTHONBIN=python
)
REM i18n support doesn't work on Windows, default to English.
set LANG=en
START /B %PYTHONBIN% scripts\mailpile %*
