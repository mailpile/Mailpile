# This is the generic auto-tagging plugin.
#
# We feed the classifier the same terms as go into the search engine,
# which should allow us to actually introspect a bit into the behavior
# of the classifier.

import math
import time
import datetime

from mailpile.commands import Command
from mailpile.config.base import ConfigDict
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils import Email
from mailpile.plugins import PluginManager
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)


##[ Configuration ]###########################################################

TAGGERS = {}
TRAINERS = {}

AUTO_TAG_CONFIG = {
    'match_tag': ['Tag we are adding to automatically', str, ''],
    'unsure_tag': ['If unsure, add to this tag', str, ''],
    'exclude_tags': ['Tags on messages we should never match (ham)', str, []],
    'ignore_kws': ['Ignore messages with these keywords', str, []],
    'corpus_size': ['How many messages do we train on?', int, 1200],
    'threshold': ['Size of the sure/unsure ranges', float, 0.1],
    'tagger': ['Internal class name or |shell command', str, ''],
    'trainer': ['Internal class name or |shell commant', str, '']}

_plugins.register_config_section(
    'prefs', 'autotag', ["Auto-tagging", AUTO_TAG_CONFIG , []])


def at_identify(at_config):
    return md5_hex(at_config.match_tag,
                   at_config.tagger,
                   at_config.trainer)[:12]


def autotag_configs(config):
    done = []
    for at_config in config.prefs.autotag:
        yield at_config
        done.append(at_config.match_tag)
    for tid, tag_info in config.tags.iteritems():
        auto_tagging = tag_info.auto_tag
        if (tid not in done and
                auto_tagging.lower() not in ('', 'off', 'false')):
            at_config = ConfigDict(_rules=AUTO_TAG_CONFIG)
            at_config.match_tag = tid
            at_config.tagger = auto_tagging
            yield at_config


class AutoTagger(object):
    def __init__(self, tagger, trainer):
        self.tagger = tagger
        self.trainer = trainer
        self.trained = False

    def reset(self, at_config):
        """Reset to an untrained state"""
        self.trainer.reset(self, at_config)
        self.trained = False

    def learn(self, *args):
        self.trained = True
        return self.trainer.learn(self, *args)

    def should_tag(self, *args):
        return self.tagger.should_tag(self, *args)


def SaveAutoTagger(config, at_config):
    aid = at_identify(at_config)
    at = config.autotag.get(aid)
    if at and at.trained:
        config.save_pickle(at, 'pickled-autotag.%s' % aid)


def LoadAutoTagger(config, at_config):
    if not config.real_hasattr('autotag'):
        config.real_setattr('autotag', {})
    aid = at_identify(at_config)
    at = config.autotag.get(aid)
    if aid not in config.autotag:
        cfn = 'pickled-autotag.%s' % aid
        try:
            config.autotag[aid] = config.load_pickle(cfn)
        except (IOError, EOFError):
            tagger = at_config.tagger
            trainer = at_config.trainer
            config.autotag[aid] = AutoTagger(
                TAGGERS.get(tagger, TAGGERS['_default'])(tagger),
                TRAINERS.get(trainer, TRAINERS['_default'])(trainer),
            )
            SaveAutoTagger(config, at_config)
    return config.autotag[aid]


# FIXME: This is dumb
import mailpile.config.manager
mailpile.config.manager.ConfigManager.load_auto_tagger = LoadAutoTagger
mailpile.config.manager.ConfigManager.save_auto_tagger = SaveAutoTagger


##[ Internal classes ]########################################################

class AutoTagCommand(object):
    def __init__(self, command):
        self.command = command


class Tagger(AutoTagCommand):
    def should_tag(self, atagger, at_config, msg, keywords):
        """Returns (result, evidence), result =True, False or None"""
        return (False, None)


class Trainer(AutoTagCommand):
    def learn(self, atagger, at_config, msg, keywords, should_tag):
        """Learn that this message should (or should not) be tagged"""
        pass

    def reset(self, atagger, at_config):
        """Reset to an untrained state (called by AutoTagger.reset)"""
        pass


TAGGERS['_default'] = Tagger
TRAINERS['_default'] = Trainer


##[ Commands ]################################################################


class AutoTagCommand(Command):
    ORDER = ('Tagging', 9)

    def _get_keywords(self, e):
        idx = self._idx()
        if not hasattr(self, 'rcache'):
            self.rcache = {}
        mid = e.msg_mid()
        if mid not in self.rcache:
            kws, snippet = idx.read_message(
                self.session,
                mid,
                e.get_msg_info(field=idx.MSG_ID),
                e.get_msg(),
                e.get_msg_size(),
                int(e.get_msg_info(field=idx.MSG_DATE), 36))
            self.rcache[mid] = kws
        return self.rcache[mid]


class Retrain(AutoTagCommand):
    SYNOPSIS = (None, 'autotag/retrain', None, '[<tags>]')

    def command(self):
        return self._retrain(tags=self.args)

    def _retrain(self, tags=None):
        "Retrain autotaggers"
        session, config, idx = self.session, self.session.config, self._idx()
        tags = tags or [asb.match_tag for asb in autotag_configs(config)]
        tids = [config.get_tag(t)._key for t in tags if t]

        session.ui.mark(_('Retraining SpamBayes autotaggers'))
        if not config.real_hasattr('autotag'):
            config.real_setattr('autotag', {})

        # Find all the interesting messages! We don't look in the trash,
        # but we do look at interesting spam.
        #
        # Note: By specifically stating that we DON'T want trash, we
        #       disable the search engine's default result suppression
        #       and guarantee these results don't corrupt the somewhat
        #       lame/broken result cache.
        #
        no_trash = ['-in:%s' % t._key for t in config.get_tags(type='trash')]
        interest = {}
        for ttype in ('replied', 'fwded', 'read', 'tagged'):
            interest[ttype] = set()
            for tag in config.get_tags(type=ttype):
                interest[ttype] |= idx.search(session,
                                              ['in:%s' % tag.slug] + no_trash
                                              ).as_set()
            session.ui.notify(_('Have %d interesting %s messages'
                                ) % (len(interest[ttype]), ttype))

        retrained, unreadable = [], []
        count_all = 0
        for at_config in autotag_configs(config):
            at_tag = config.get_tag(at_config.match_tag)
            if at_tag and at_tag._key in tids:
                session.ui.mark('Retraining: %s' % at_tag.name)

                yn = [(set(), set(), 'in:%s' % at_tag.slug, True),
                      (set(), set(), '-in:%s' % at_tag.slug, False)]

                # Get the current message sets: tagged and untagged messages
                # excluding trash.
                for tset, mset, srch, which in yn:
                    mset |= idx.search(session, [srch] + no_trash).as_set()

                # If we have any exclude_tags, they are particularly
                # interesting, so we'll look at them first.
                interesting = []
                for etagid in at_config.exclude_tags:
                    etag = config.get_tag(etagid)
                    if etag._key not in interest:
                        srch = ['in:%s' % etag._key] + no_trash
                        interest[etag._key] = idx.search(session, srch
                                                         ).as_set()
                    interesting.append(etag._key)
                interesting.extend(['replied', 'fwded', 'read', 'tagged',
                                    None])

                # Go through the interest types in order of preference and
                # while we still lack training data, add to the training set.
                for ttype in interesting:
                    for tset, mset, srch, which in yn:
                        # False positives are really annoying, and generally
                        # speaking any autotagged subset should be a small
                        # part of the Universe. So we divide the corpus
                        # budget 33% True, 67% False.
                        full_size = int(at_config.corpus_size *
                                        (0.33 if which else 0.67))
                        want = min(full_size // 4,
                                   max(0, full_size - len(tset)))
                        if want:
                            if ttype:
                                adding = sorted(list(mset & interest[ttype]))
                            else:
                                adding = sorted(list(mset))
                            adding = set(list(reversed(adding))[:want])
                            tset |= adding
                            mset -= adding

                # Load classifier, reset
                atagger = config.load_auto_tagger(at_config)
                atagger.reset(at_config)
                for tset, mset, srch, which in yn:
                    count = 0
                    # We go through the liste of message in order, to avoid
                    # thrashing caches too badly.
                    for msg_idx in sorted(list(tset)):
                        try:
                            e = Email(idx, msg_idx)
                            count += 1
                            count_all += 1
                            session.ui.mark(
                                _('Reading %s (%d/%d, %s=%s)'
                                  ) % (e.msg_mid(), count, len(tset),
                                       at_tag.name, which))
                            atagger.learn(at_config,
                                          e.get_msg(),
                                          self._get_keywords(e),
                                          which)
                        except (IndexError, TypeError, ValueError,
                                OSError, IOError):
                            if session.config.sys.debug:
                                import traceback
                                traceback.print_exc()
                            unreadable.append(msg_idx)
                            session.ui.warning(
                                _('Failed to process message at =%s'
                                  ) % (b36(msg_idx)))

                # We got this far without crashing, so save the result.
                config.save_auto_tagger(at_config)
                retrained.append(at_tag.name)

        message = _('Retrained SpamBayes auto-tagging for %s'
                    ) % ', '.join(retrained)
        session.ui.mark(message)
        return self._success(message, result={
            'retrained': retrained,
            'unreadable': unreadable,
            'read_messages': count_all
        })

    @classmethod
    def interval_retrain(cls, session):
        """
        Retrains autotaggers

        Classmethod used for periodic automatic retraining
        """
        result = cls(session)._retrain()
        if result:
            return True
        else:
            return False


_plugins.register_config_variables('prefs', {
    'autotag_retrain_interval': [
        _('Periodically retrain autotagger (seconds)'), int, 24*60*60]})

_plugins.register_slow_periodic_job(
    'retrain_autotag',
    'prefs.autotag_retrain_interval',
    Retrain.interval_retrain)


class Classify(AutoTagCommand):
    SYNOPSIS = (None, 'autotag/classify', None, '<msgs>')
    ORDER = ('Tagging', 9)

    def _classify(self, emails):
        session, config, idx = self.session, self.session.config, self._idx()
        results = {}
        unknown = []
        for e in emails:
            kws = self._get_keywords(e)
            result = results[e.msg_mid()] = {}
            for at_config in autotag_configs(config):
                if not at_config.match_tag:
                    continue
                at_tag = config.get_tag(at_config.match_tag)
                if not at_tag and at_config.match_tag not in unknown:
                    session.ui.error(_('Unknown tag: %s'
                                       ) % at_config.match_tag)
                    unknown.append(at_config.match_tag)
                    continue

                atagger = config.load_auto_tagger(at_config)
                if atagger.trained:
                    result[at_tag._key] = result.get(at_tag._key, [])
                    result[at_tag._key].append(atagger.should_tag(
                        at_config, e.get_msg(), kws
                    ))
        return results

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]
        return self._success(_('Classified %d messages') % len(emails),
                             self._classify(emails))


class AutoTag(Classify):
    SYNOPSIS = (None, 'autotag', None, '<msgs>')
    ORDER = ('Tagging', 9)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]
        scores = self._classify(emails)
        tag = {}
        for mid in scores:
            for at_config in autotag_configs(config):
                at_tag = config.get_tag(at_config.match_tag)
                if not at_tag:
                    continue
                want = scores[mid].get(at_tag._key, (False, ))[0]

                if want is True:
                    if at_config.match_tag not in tag:
                        tag[at_config.match_tag] = [mid]
                    else:
                        tag[at_config.match_tag].append(mid)

                elif at_config.unsure_tag and want is None:
                    if at_config.unsure_tag not in tag:
                        tag[at_config.unsure_tag] = [mid]
                    else:
                        tag[at_config.unsure_tag].append(mid)

        for tid in tag:
            idx.add_tag(session, tid, msg_idxs=[int(i, 36) for i in tag[tid]])

        return self._success(_('Auto-tagged %d messages') % len(emails), tag)


_plugins.register_commands(Retrain, Classify, AutoTag)


##[ Keywords ]################################################################

def filter_hook(session, msg_mid, msg, keywords, **kwargs):
    """Classify this message."""
    if not kwargs.get('incoming', False):
        return keywords

    config = session.config
    for at_config in autotag_configs(config):
        try:
            at_tag = config.get_tag(at_config.match_tag)
            atagger = config.load_auto_tagger(at_config)
            if not atagger.trained:
                continue
            want, info = atagger.should_tag(at_config, msg, keywords)
            if want is True:
                if 'autotag' in config.sys.debug:
                    session.ui.debug(('Autotagging %s with %s (w=%s, i=%s)'
                                      ) % (msg_mid, at_tag.name, want, info))
                keywords.add('%s:in' % at_tag._key)
            elif at_config.unsure_tag and want is None:
                unsure_tag = config.get_tag(at_config.unsure_tag)
                if 'autotag' in config.sys.debug:
                    session.ui.debug(('Autotagging %s with %s (w=%s, i=%s)'
                                      ) % (msg_mid, unsure_tag.name,
                                           want, info))
                keywords.add('%s:in' % unsure_tag._key)
        except (KeyError, AttributeError, ValueError):
            pass

    return keywords


# We add a filter pre-hook with a high (late) priority.  Late priority to
# maximize the amount of data we are feeding to the classifier, but a
# pre-hook so normal filter rules will override the autotagging.
_plugins.register_filter_hook_pre('90-autotag', filter_hook)
