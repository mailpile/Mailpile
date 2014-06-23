@echo off
set PYTHONPATH=%~dp0
if exist c:\python27\python.exe (
  set PYTHONBIN=c:\python27\python.exe
) else (
  set PYTHONBIN=python
)
echo Please Wait While We Get And Install The Requirements
%PYTHONBIN% -m pip install "Jinja2"
%PYTHONBIN% -m pip install "spambayes>=1.1b1"
%PYTHONBIN% -m pip install "selenium>=2.40.0"
%PYTHONBIN% -m pip install "markupsafe"
%PYTHONBIN% -m pip install "nose"
%PYTHONBIN% -m pip install "mock>=1.0.1"
%PYTHONBIN% -m pip install "colorama"
echo Install Is Finished
PAUSE%*