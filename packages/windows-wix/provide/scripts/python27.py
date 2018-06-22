import os.path
import glob
import subprocess


def bind(framework):

    @framework.provide('python27')
    def provide_python27(build, keyword):
        '''
        provide python27 prepared for mailpile
        '''

        build.depend('root')
        dep_path = build.invoke('path', keyword)

        extractor = build.depend('extract_msi')
        extractor(build.cache().resource(keyword), dep_path)

        util = build.depend('util')
        util.publish_exes(build, dep_path)

        # Rebrand with resource hacker--very finicky
        # https://www.askvg.com/tutorial-all-about-resource-hacker-in-a-brief-tutorial/
        #
        mailpile_dir = build.depend('mailpile')
        assets_dir = os.path.join(
            mailpile_dir, 'packages\\windows-wix\\assets')
        resource_hacker = os.path.join(build.depend('resource_hacker'),
                                       'ResourceHacker.exe')
        for exe in ('python.exe', 'pythonw.exe'):
            exe_path = os.path.join(dep_path, exe)
            update_path = os.path.join(
                dep_path, exe.replace('.', '-mailpile.'))
            cmd = ('-open', exe_path,
                   '-save', update_path,
                   '-action', 'addoverwrite',
                   '-resource', os.path.join(assets_dir, 'mailpile_logo.ico'),
                   '-mask', 'ICONGROUP,1,0')
            build.invoke('ResourceHacker', *cmd)
            build.publish(exe.split('.')[0],
                          framework.Invoker(build, update_path))
            util.rmtree(exe_path)

        # TODO: Prune unwanted files--either via features or manual delete.
        #
        for item in ('tcl','Lib\\test'):
            build.log().info("Removing directory '{}'".format(item))
            util.rmtree(os.path.join(dep_path,item))

        # Manually bootstrap pip.
        # https://stackoverflow.com/questions/36132350/install-python-wheel-file-without-using-pip
        #
        build.log().debug('Bootstrapping pip from bundled wheels')
        bundle_dir = os.path.join(dep_path, 'Lib\\ensurepip\\_bundled')
        pip_wheel = next(glob.iglob(os.path.join(bundle_dir, 'pip*.whl')))
        setup_wheel = next(glob.iglob(os.path.join(bundle_dir, 'setup*.whl')))

        tmp_pip = os.path.join(pip_wheel, 'pip')
        build.invoke('python', tmp_pip, 'install', setup_wheel)
        build.invoke('python', tmp_pip, 'install', pip_wheel)

        # Use pip to install dependencies
        # TODO: Cache/statically version packages.
        #
        pip_deps = os.path.join(mailpile_dir, 'requirements.txt')
        build.invoke('python', '-m', 'pip', 'install', '-r', pip_deps)

        # TODO: import requirements from gui-o-matic
        #
        build.invoke('python', '-m', 'pip', 'install', 'pywin32')

        return dep_path
