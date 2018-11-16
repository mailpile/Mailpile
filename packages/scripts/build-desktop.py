#!/usr/bin/python
"""
build-desktop.py - Checkout and build Mailpile for desktop platforms (win/mac)

Usage: build-desktop.py [clean] <nightly|release>

"""
import os
import subprocess
import sys
import traceback


DEBUG = True
GIT_BINARY = 'git'


##[ Boilerplate to make scripts more readable... ]############################

class Sub(object):
    def __init__(self, command, env=None):
        self.command = command
        self.stdout = self.stderr = self.rcode = ''
        self.env = env

    def communicate(self):
        process = subprocess.Popen(
            self.command,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        self.stdout = stdout.decode('utf-8')
        self.stderr = stderr.decode('utf-8')
        self.rcode = process.poll()

    def __str__(self):
        return (
            '###[ %s ]###\n==[STDOUT]==\n%s\n==[STDERR]==\n%s\n==[RCODE: %s]\n'
            % (' '.join(self.command), self.stdout, self.stderr, self.rcode))


def run(*args, **kwargs):
    result = Sub(args, env=kwargs.get('env'))
    try:
        result.communicate()
        if DEBUG:
            print('%s' % result)
        if kwargs.get('_raise') and result.rcode != 0:
            raise kwargs.get('_raise')('Returned: %s' % result.rcode)
    except Exception as e:
        traceback.print_exc()
    return result


def git(*args, **kwargs):
    return run(*([GIT_BINARY] + list(args)), **kwargs)


##[ Actual build rules... ]###################################################

def macOS_build(mailpile_tree, repo, branch, clean_build):
    os.chdir(os.path.join(mailpile_tree, 'packages', 'macos'))
    build_dir = os.path.expanduser('~/build-%s' % repo)

    if clean_build and os.path.exists(build_dir) and os.path.isdir(build_dir):
        sub('rm', '-rf', build_dir)

    run('./build.sh', env={'BUILD_DIR': build_dir}, _raise=ValueError)


def windows_build(mailpile_tree, repo, branch, clean_build):
    os.chdir(os.path.join(mailpile_tree, 'packages', 'windows-wix'))
    build_dir = os.path.expanduser('~/build-%s' % repo)

    if clean_build and os.path.exists(build_dir) and os.path.isdir(build_dir):
        sub('bash', '-c', 'rm -rf "%s"' % build_dir)

    run('python', 'provide', '-i', 'provide.json', _raise=ValueError)


if __name__ == '__main__':
    os.chdir(os.path.dirname(__file__) or '.')
    if len(sys.argv) < 2:
        print(__doc__)
        print('\nERROR: Missing arguments! What to do?')
        sys.exit(1)

    force_build = True
    clean_build = False
    repo = 'nightly'
    branch = 'master'
    for arg in sys.argv[1:]:
        if arg == 'clean':
            clean_build = True
            force_build = True
            continue
        elif arg == 'force':
            force_build = True
            continue
        elif arg == 'nightly':
            repo, branch = 'nightly', 'master'
        elif arg == 'release':
            repo, branch = 'release', 'release/1.0'
        else:
            print(__doc__)
            print('\nERROR: Unrecognized argument: %s' % arg)
            sys.exit(2)

        # Ensure ~/Mailpile exists and has a Mailpile tree
        mailpile_tree = os.path.expanduser('~/Mailpile')
        try:
            os.chdir(mailpile_tree)
            if not os.path.exists('.git'):
                raise OSError('Boo')
        except OSError:
            if not os.path.exists(mailpile_tree):
                os.mkdir(mailpile_tree)
            os.chdir(mailpile_tree)
            git('clone', '--recurse-submodules',
                'https://github.com/Mailpile/mailpile/', '.',
                _raise=ValueError)

        # Check out and update the requested branch, triggering a build if we
        # are either forcing or if something has changed.
        git('checkout', '-f', branch, _raise=True)
        if (force_build or clean_build or
                'up to date' not in git('pull', 'origin', branch).stdout):

            git('pull', '--recurse-submodules', 'origin', branch,
                _raise=ValueError)

            if sys.platform == 'darwin':
                macOS_build(mailpile_tree, repo, branch, clean_build)

            elif sys.platform.startswith('win'):
                windows_build(mailpile_tree, repo, branch, clean_build)

            else:
                print(__doc__)
                print('\nERROR: Unknown platform: %s' % sys.platform)
                sys.exit(3)

# EOF #
