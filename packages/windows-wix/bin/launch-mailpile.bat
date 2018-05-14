SET MAILPILE_ROOT=%~dp0

Start "" "%MAILPILE_ROOT%..\Python27\pythonw-mailpile.exe" "%MAILPILE_ROOT%\with-mailpile-env.py" -q "%MAILPILE_ROOT%..\Mailpile\shared-data\mailpile-gui\mailpile-gui.py"