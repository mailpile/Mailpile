@echo off
set PYTHONPATH=%~dp0
if exist c:\python27\python.exe (
  set PYTHONBIN=c:\python27\python.exe
) else (
  set PYTHONBIN=python
)
echo Please Wait While We Get And Install The Requirements
c:\python27\python.exe -m pip install -r requirements.txt 
echo Install Is Finished
PAUSE%*