import textwrap
import os


def bind(build):

    @build.provide('gpg')
    def provide_gpg(build, keyword):
        '''
        install GPG in a temporary location and use mkportable to create a
        portable GPG for the build. Requires ADMIN and that gpg4win *is not*
        installed.
        '''
        build.depend('root')
        dep_path = build.invoke('path', keyword)

        util = build.depend('util')

        build.depend('python27')
        gpg_installer = build.cache().resource('gpg')

        gpg_ini = textwrap.dedent('''
            [gpg4win]
                inst_gpgol = false
                inst_gpgex = false
                inst_kleopatra = false
                inst_gpa = false
                inst_claws_mail = false
                inst_compendium = false
                inst_start_menu = false
                inst_desktop = false
                inst_quick_launch_bar = false
            ''')

        # Use the built python to elevate if needed
        # https://stackoverflow.com/questions/130763/request-uac-elevation-from-within-a-python-script
        build_template = textwrap.dedent('''
            #!/usr/bin/python
            import sys
            import ctypes
            import subprocess
            import os.path
            import win32com.shell.shell as shell
            import win32com.shell.shellcon as shellcon
            import win32event
            import win32process
            import win32api
            import win32con
            import socket
            import random
            import traceback

            def make_portable_gpg():
                install_cmd = ("{installer_path}", "/S",
                               "/C={config}",
                               "/D={target}")
                uninstall_cmd = ("{uninstaller_path}", "/S")
                portable_cmd = ("{mkportable_path}", "{build}")
                
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                subprocess.check_call( install_cmd, startupinfo = si )
                subprocess.check_call( portable_cmd, startupinfo = si )
                subprocess.check_call( uninstall_cmd, startupinfo = si )

            def ellevate_and_wait( sock, timeout ):
                sock.settimeout( timeout )
                while True:
                    try:
                        port = random.randint(1000, 2**16-1)
                        sock.bind( ("localhost", port) )
                        break
                    except socket.error:
                        continue

                parameters = '"{{}}" {{}}'.format( os.path.abspath( __file__ ), port )
                result = shell.ShellExecuteEx(fMask = shellcon.SEE_MASK_NOCLOSEPROCESS,
                                              lpVerb = "runas",
                                              lpFile = sys.executable,
                                              lpParameters = parameters,
                                              nShow = win32con.SW_HIDE )

                handle = result['hProcess']
                status = win32event.WaitForSingleObject(handle, -1)
                win32api.CloseHandle( handle )
                return sock.recv( 4096*1024 )

            def signal_result_and_exit( sock, error_message = '' ):
                if len( sys.argv ) > 1:
                    port = int( sys.argv[1] )
                    sock.sendto(error_message.encode(), ("localhost", port))
                else:
                    sys.stderr.write(error_message)
                sys.exit( len( error_message ) )

            try:
                sock = socket.socket( socket.AF_INET, socket.SOCK_DGRAM )    
                if ctypes.windll.shell32.IsUserAnAdmin():
                    try:
                        make_portable_gpg()
                        result = ''
                    except:
                        result = traceback.format_exc()
                else:
                    result = ellevate_and_wait( sock, 14 )

                signal_result_and_exit( sock, result )

            finally:
                sock.close()
            ''')

        def script_escape(value):
            '''
            Escape text literals for generated script
            '''

            return value.replace('\\', '\\\\')

        os.mkdir(dep_path)

        with util.temporary_scope() as scope:
            tmp_path = scope.named_dir()
            uninstaller = os.path.join(tmp_path, "gpg4win-uninstall.exe")
            mkportable = os.path.join(tmp_path, "bin\\mkportable.exe")

            script_vars = {'installer_path': script_escape(gpg_installer),
                           'uninstaller_path': script_escape(uninstaller),
                           'mkportable_path': script_escape(mkportable),
                           'build': script_escape(dep_path),
                           'target': script_escape(tmp_path)}

            with scope.named_file() as ini_file:
                ini_file.write(gpg_ini.encode())
                script_vars['config'] = script_escape(ini_file.name)

            with scope.named_file() as build_script:
                build_script.write(
                    build_template.format(**script_vars).encode())
                #print build_template.format( **script_vars )
                script_path = build_script.name

            build.invoke('python', script_path)

        return dep_path
