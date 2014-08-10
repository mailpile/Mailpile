; SetCompressor /SOLID lzma

!include "MUI2.nsh"
!define MUI_ICON "mailpile.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "mailpile_logo.bmp"
!define MUI_ABORTWARNING
!insertmacro MUI_LANGUAGE "English"

InstallDir "$LOCALAPPDATA\Mailpile"
Name Mailpile
  
;Get installation folder from registry if available
InstallDirRegKey HKCU "Software\Mailpile" ""

;Request application privileges for Windows Vista
RequestExecutionLevel user

OutFile "Mailpile Installer.exe"

!insertmacro MUI_PAGE_LICENSE "../../COPYING.md"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
  
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

 
Section
	SetOutPath $INSTDIR

	WriteUninstaller $INSTDIR\uninstall.exe

	WriteRegStr HKCU "Software\Mailpile" "" $INSTDIR

	File /r /x packages /x junk /x .git "../../../Mailpile/*"
	File /r "GnuPG"
	File /r "OpenSSL"
	File /r "Python27"
	File "mailpile.ico"
	File "launcher.exe"
	File "launcher.exe.config"
	File /r "img"

	createDirectory "$SMPROGRAMS\Mailpile"
	createShortCut "$SMPROGRAMS\Mailpile\Start Mailpile.lnk" "$INSTDIR\launcher.exe" "" "$INSTDIR\mailpile.ico" # Call startup script...
	WriteINIStr "$SMPROGRAMS\Mailpile\Open Mailpile.url" "InternetShortcut" "URL" "http://localhost:33411"
	

	WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Run" \
			"Mailpile" "$INSTDIR\mp.cmd"
SectionEnd


Section "un.Uninstall"
	RMDir "$INSTDIR"
	Delete "$SMPROGRAMS\Mailpile\Start Mailpile.lnk"
	Delete "$SMPROGRAMS\Mailpile\Open Mailpile.url"
	RMDir "$SMPROGRAMS\Mailpile"

	DeleteRegKey /ifempty HKCU "Software\Mailpile"
SectionEnd
