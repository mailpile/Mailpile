SetCompressor /SOLID lzma

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

	createShortCut "$SMPROGRAMS\Mailpile.lnk" "$INSTDIR\mailpile\mp.cmd" # Call startup script...

	File /r /x packages /x .git "../../../Mailpile/*"
	File /r "GnuPG"
	File /r "OpenSSL"
	File /r "Python27"

	WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Run" \
			"Mailpile" "$INSTDIR\mp.cmd"
SectionEnd


Section "un.Uninstall"
	RMDir "$INSTDIR"
	Delete "$SMPROGRAMS\Mailpile.lnk"

	DeleteRegKey /ifempty HKCU "Software\Mailpile"
SectionEnd
