import getopt
import gettext
import locale
import os
import sys
from gettext import gettext as _

import mailpile.util
import mailpile.defaults
from mailpile.commands import COMMANDS, Action, Help, HelpSplash, Load, Rescan
from mailpile.config import ConfigManager, getLocaleDirectory
from mailpile.ui import ANSIColors, Session, UserInteraction, Completer
from mailpile.util import *

# This makes sure mailbox "plugins" get loaded... has to go somewhere?
from mailpile.mailboxes import *

# This is also a bit silly, should be somewhere else?
Help.ABOUT = mailpile.defaults.ABOUT

# We may try to load readline later on... maybe?
readline = None


##[ Main ]####################################################################


def Interact(session):
    global readline
    try:
        import readline as rl  # Unix-only
        readline = rl
    except ImportError:
        pass

    try:
        if readline:
            readline.read_history_file(session.config.history_file())
            readline.set_completer_delims(Completer.DELIMS)
            readline.set_completer(Completer(session).get_completer())
            for opt in ["tab: complete", "set show-all-if-ambiguous on"]:
                readline.parse_and_bind(opt)
    except IOError:
        pass

    # Negative history means no saving state to disk.
    history_length = session.config.sys.history_length
    if readline is None:
        pass  # history currently not supported under Windows / Mac
    elif history_length >= 0:
        readline.set_history_length(history_length)
    else:
        readline.set_history_length(-history_length)

    try:
        prompt = session.ui.term.color('mailpile> ',
                                       color=session.ui.term.BLACK,
                                       weight=session.ui.term.BOLD)
        while not mailpile.util.QUITTING:
            session.ui.block()
            opt = raw_input(prompt).decode('utf-8').strip()
            session.ui.term.check_max_width()
            session.ui.unblock()
            if opt:
                if ' ' in opt:
                    opt, arg = opt.split(' ', 1)
                else:
                    arg = ''
                try:
                    session.ui.display_result(Action(session, opt, arg))
                except UsageError, e:
                    session.error(unicode(e))
                except UrlRedirectException, e:
                    session.error('Tried to redirect to: %s' % e.url)
    except EOFError:
        print
    finally:
        session.ui.unblock()

    try:
        if session.config.sys.history_length > 0:
            readline.write_history_file(session.config.history_file())
        else:
            os.remove(session.config.history_file())
    except OSError:
        pass


def Main(args):
    # Bootstrap translations until we've loaded everything else
    translation = gettext.translation("mailpile", getLocaleDirectory(),
                                      fallback=True)
    translation.install(unicode=True)

    try:
        # Create our global config manager and the default (CLI) session
        config = ConfigManager(rules=mailpile.defaults.CONFIG_RULES)
        session = Session(config)
        cli_ui = session.ui = UserInteraction(config)
        session.main = True
        session.config.load(session)
    except AccessError, e:
        sys.stderr.write('Access denied: %s\n' % e)
        sys.exit(1)

    try:
        # Create and start (most) worker threads
        config.prepare_workers(session)

        try:
            shorta, longa = '', []
            for cls in COMMANDS:
                shortn, longn, urlpath, arglist = cls.SYNOPSIS[:4]
                if arglist:
                    if shortn:
                        shortn += ':'
                    if longn:
                        longn += '='
                if shortn:
                    shorta += shortn
                if longn:
                    longa.append(longn.replace(' ', '_'))

            opts, args = getopt.getopt(args, shorta, longa)
            for opt, arg in opts:
                session.ui.display_result(Action(
                    session, opt.replace('-', ''), arg.decode('utf-8')))
            if args:
                session.ui.display_result(Action(
                    session, args[0], ' '.join(args[1:]).decode('utf-8')))

        except (getopt.GetoptError, UsageError), e:
            session.error(unicode(e))

        if not opts and not args:
            # Create and start the rest of the threads, load the index.
            session.interactive = session.ui.interactive = True
            if sys.stdout.isatty():
                session.ui.term = ANSIColors()

            config.prepare_workers(session, daemons=True)
            Load(session, '').run(quiet=True)
            session.ui.display_result(HelpSplash(session, 'help', []).run())
            Interact(session)

    except KeyboardInterrupt:
        pass

    finally:
        if readline:
            readline.write_history_file(session.config.history_file())

        # Make everything in the background quit ASAP...
        mailpile.util.LAST_USER_ACTIVITY = 0
        mailpile.util.QUITTING = True

        config.plugins.process_shutdown_hooks()
        config.flush_mbox_cache(session, wait=True)
        config.stop_workers()
        if config.index:
            config.index.save_changes()

        if session.interactive and config.sys.debug:
            session.ui.display_result(Action(session, 'ps', ''))

if __name__ == "__main__":
    Main(sys.argv[1:])
