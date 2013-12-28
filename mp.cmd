@echo off
set PYTHONPATH=%~dp0
if exist c:\python27\python.exe (
  set PYTHONBIN=c:\python27\python.exe
) else (
  set PYTHONBIN=python
)
%PYTHONBIN% scripts\mailpile %*
