; SetCompressor /SOLID lzma

!include "MUI2.nsh"
!define MUI_ICON "packages\windows\mailpile.ico"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_BITMAP "packages\windows\mailpile_logo.bmp"
!define MUI_ABORTWARNING
!insertmacro MUI_LANGUAGE "English"

InstallDir "$PROGRAMFILES\Mailpile"
Name Mailpile
  
;Get installation folder from registry if available
InstallDirRegKey HKCU "Software\Mailpile" ""

;Request application privileges for Windows Vista
RequestExecutionLevel user

OutFile "Mailpile-Installer.exe"

!insertmacro MUI_PAGE_LICENSE "COPYING.md"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
  
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

Section
	SetOutPath $INSTDIR

	WriteUninstaller $INSTDIR\uninstall.exe

	WriteRegStr HKCU "Software\Mailpile" "" $INSTDIR

	File /r /x junk /x macosx /x tmp /x .git /x testing "*.*"

	createDirectory "$SMPROGRAMS\Mailpile"
	createShortCut "$SMPROGRAMS\Mailpile\Start Mailpile.lnk" "$INSTDIR\Mailpile.exe" "" "$INSTDIR\packages\windows\mailpile.ico"
	WriteINIStr "$SMPROGRAMS\Mailpile\Open Mailpile.url" "InternetShortcut" "URL" "http://localhost:33411"
	createShortCut "$SMPROGRAMS\Mailpile\Uninstall Mailpile.lnk" "$INSTDIR\uninstall.exe" "" ""

	WriteRegStr HKEY_LOCAL_MACHINE "Software\Microsoft\Windows\CurrentVersion\Run" \
			"Mailpile" "$INSTDIR\mailpile.exe"
SectionEnd

Section "un.Uninstall"
	RMDir /r "$SMPROGRAMS\Mailpile"
	RMDir /r "$INSTDIR"
	DeleteRegKey HKCU "Software\Mailpile"
SectionEnd
