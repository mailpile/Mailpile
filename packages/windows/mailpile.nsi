OutFile "Mailpile Installer.exe"

InstallDir "C:\Program Files\Mailpile\"

PageEx license
	LicenseData "../../COPYING.md"
	LicenseForceselection checkbox
PageExEnd
Page directory
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles

SetCompressor /SOLID lzma
 
Section
	SetOutPath $INSTDIR

	WriteUninstaller $INSTDIR\uninstall.exe

	createShortCut "$SMPROGRAMS\Mailpile.lnk" "$INSTDIR\mailpile" # Call startup script...

	File /r /x packages /x .git "../../../Mailpile/*"
	File /r "GnuPG"
	File /r "OpenSSL"
	File /r "Python27"
SectionEnd


Section "un.Uninstall"
	Delete "$INSTDIR"
	Delete "$SMPROGRAMS\Mailpile.lnk"
SectionEnd
