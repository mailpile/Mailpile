# This is an auto-tagging plugin that uses SpamBayes to classify messages.
#
# We feed the classifier the same terms as go into the search engine,
# which should allow us to actually introspect a bit into the behavior
# of the classifier.

import math
import time
import datetime
from gettext import gettext as _

from spambayes.classifier import Classifier

import mailpile.config
import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email


##[ Configuration ]###########################################################

mailpile.plugins.register_config_section('prefs', 'autotag_sb', ["Spambayes",
{
    'match_tag': ['Tag we are adding to automatically', str, ''],
    'unsure_tag': ['If unsure, add to this tag', str, ''],
    'exclude_tags': ['Tags on messages we should never match (ham)', str, []],
    'ignore_kws': ['Ignore messages with these keywords', str, []],
    'corpus_size': ['How many messages do we train on?', int, 1000],
    'threshold': ['Size of the sure/unsure ranges', float, 0.1],
}, []])


def SaveClassifier(config, match_tag):
    if config.autotag_sb[match_tag].trained:
        config.save_pickle(config.autotag_sb[match_tag],
                           'pickled-autotag_sb.%s' % match_tag)


def LoadClassifier(config, match_tag):
    if not hasattr(config, 'autotag_sb'):
        config.autotag_sb = {}
    if match_tag not in config.autotag_sb:
        cfn = 'pickled-autotag_sb.%s' % match_tag
        try:
            config.autotag_sb[match_tag] = config.load_pickle(cfn)
            config.autotag_sb[match_tag].trained = True
        except IOError:
            config.autotag_sb[match_tag] = Classifier()
            config.autotag_sb[match_tag].trained = False
            SaveClassifier(config, match_tag)
        config.autotag_sb[match_tag].setup()
    return config.autotag_sb[match_tag]


mailpile.config.ConfigManager.load_sb_classifier = LoadClassifier;
mailpile.config.ConfigManager.save_sb_classifier = SaveClassifier;


##[ Commands ]################################################################


class AutoTagCommand(Command):
    ORDER = ('Tagging', 9)

    def _get_keywords(self, e):
        idx = self._idx()
        if not hasattr(self, 'rcache'):
            self.rcache = {}
        mid = e.msg_mid()
        if mid not in self.rcache:
            kws, snippet = idx.read_message(self.session,
                mid,
                e.get_msg_info(field=idx.MSG_ID),
                e.get_msg(),
                e.get_msg_size(),
                int(e.get_msg_info(field=idx.MSG_DATE), 36)
            )
            self.rcache[mid] = kws
        return self.rcache[mid]


#   - Add a command for retraining a particular tag, or all tags.
#       - Should collect N messages for training, prefer messages
#         that are interesting - having been read, replied to, tagged
#         by hand or placed in the "ham" corpus.
#       - Pad up to corpus_size with random selection biased towards
#         recent mail?
class Retrain(AutoTagCommand):
    SYNOPSIS = (None, 'autotag_sb/retrain', None, '[<tags>]')

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        tags = self.args or [asb['match_tag']
                             for asb in config.prefs.autotag_sb]
        tids = [config.get_tag(t)._key for t in tags if t]

        session.ui.mark(_('Retraining SpamBayes autotaggers'))
        if not hasattr(config, 'autotag_sb'):
            config.autotag_sb = {}

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
        for ttype in ('replied', 'read', 'tagged'):
            interest[ttype] = set()
            for tag in config.get_tags(type=ttype):
                interest[ttype] |= idx.search(session,
                                              ['in:%s' % tag.slug] + no_trash
                                              ).as_set()
            session.ui.notify(_('Have %d interesting %s messages'
                                ) % (len(interest[ttype]), ttype))

        retrained = []
        count_all = 0
        for asb in config.prefs.autotag_sb:
            asb_tag = config.get_tag(asb.match_tag)
            if asb_tag and asb_tag._key in tids:
                session.ui.mark('Retraining: %s' % asb_tag.name)

                yn = [(set(), set(), 'in:%s' % asb_tag.slug, True),
                      (set(), set(), '-in:%s' % asb_tag.slug, False)]

                # Get the current message sets: tagged and untagged messages
                # excluding trash.
                for tset, mset, srch, which in yn:
                    mset |= idx.search(session, [srch] + no_trash).as_set()

                # If we have any exclude_tags, they are particularly
                # interesting, so we'll look at them first.
                interesting = []
                for etagid in asb.exclude_tags:
                    etag = config.get_tag(etagid)
                    if etag._key not in interest:
                        srch = ['in:%s' % etag._key] + no_trash
                        interest[etag._key] = idx.search(session, srch
                                                         ).as_set()
                    interesting.append(etag._key)
                interesting.extend(['replied', 'read', 'tagged', None])

                # Go through the interest types in order of preference and
                # while we still lack training data, add to the training set.
                for ttype in interesting:
                    for tset, mset, srch, which in yn:
                        # FIXME: Is this a good idea? No single data source
                        # is allowed to be more than 50% of the corpus, to
                        # try and encourage diversity.
                        want = min(asb.corpus_size / 4,
                                   max(0, asb.corpus_size / 2 - len(tset)))
                        if want:
                            if ttype:
                                adding = sorted(list(mset & interest[ttype]))
                            else:
                                adding = sorted(list(mset))
                            adding = set(list(reversed(adding))[:want])
                            tset |= adding
                            mset -= adding

                # Start with a fresh classifier
                bayes = Classifier()
                for tset, mset, srch, which in yn:
                    count = 0
                    for msg_idx in tset:
                        e = Email(idx, msg_idx)
                        count += 1
                        count_all += 1
                        session.ui.mark(('Reading %s (%d/%d, %s=%s)'
                                         ) % (e.msg_mid(), count, len(tset),
                                              asb_tag.name, which))
                        bayes.learn(self._get_keywords(e), which)

                # We got this far without crashing, so save the result.
                bayes.trained = True
                config.autotag_sb[asb_tag._key] = bayes
                config.save_sb_classifier(asb_tag._key)
                retrained.append(asb_tag.name)

        session.ui.mark(_('Retrained SpamBayes auto-tagging for %s'
                          ) % ', '.join(retrained))
        return {'retrained': retrained, 'read_messages': count_all}


class Classify(AutoTagCommand):
    SYNOPSIS = (None, 'autotag_sb/classify', None, '<msgs>')
    ORDER = ('Tagging', 9)

    def _classify(self, emails):
        session, config, idx = self.session, self.session.config, self._idx()
        results = {}
        unknown = []
        for e in emails:
            kws = self._get_keywords(e)
            result = results[e.msg_mid()] = {}
            for asb in config.prefs.autotag_sb:
                if not asb.match_tag:
                    continue
                    continue
                asb_tag = config.get_tag(asb.match_tag)
                if not asb_tag and asb.match_tag not in unknown:
                    session.ui.error(_('Unknown tag: %s') % asb.match_tag)
                    unknown.append(asb.match_tag)
                    continue
                bayes = config.load_sb_classifier(asb_tag._key)
                if bayes.trained:
                    prob, evidence = bayes.chi2_spamprob(kws, evidence=True)
                    result[asb_tag._key] = (prob, evidence)
        return results

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]
        return self._classify(emails)


class AutoTag(Classify):
    SYNOPSIS = (None, 'autotag_sb', None, '<msgs>')
    ORDER = ('Tagging', 9)

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        emails = [Email(idx, mid) for mid in self._choose_messages(self.args)]
        scores = self._classify(emails)
        tag = {}
        for mid in scores:
            for asb in config.prefs.autotag_sb:
                asb_tag = config.get_tag(asb.match_tag)
                if not asb_tag:
                    continue
                score = scores[mid].get(asb_tag._key, (0, ))[0]

                if score > (1.0 - asb.threshold):
                    if asb.match_tag not in tag:
                        tag[asb.match_tag] = [mid]
                    else:
                        tag[asb.match_tag].append(mid)

                elif asb.unsure_tag and score >= asb.threshold:
                    if asb.unsure_tag not in tag:
                        tag[asb.unsure_tag] = [mid]
                    else:
                        tag[asb.unsure_tag].append(mid)

        for tid in tag:
            idx.add_tag(session, tid, msg_idxs=[int(i, 36) for i in tag[tid]])

        return tag


mailpile.plugins.register_commands(Retrain, Classify, AutoTag)


##[ Cron jobs ]###############################################################

# FIXME: We should periodically retrain?


##[ Keywords ]################################################################

def filter_hook(session, msg_mid, msg, keywords):
    """Classify this message."""
    config = session.config
    for asb in config.prefs.autotag_sb:
        try:
            asb_tag = config.get_tag(asb.match_tag)
            bayes = config.load_sb_classifier(asb_tag._key)
            if not bayes.trained:
                continue
            score = bayes.chi2_spamprob(keywords)
            if score > (1 - asb.threshold):
                if 'autotag' in config.sys.debug:
                    session.ui.debug(('Autotagging %s with %s (score=%.3f)'
                                      ) % (msg_mid, asb_tag.name, score))
                keywords.add('%s:tag' % asb_tag._key)
            elif asb.unsure_tag and score >= asb.threshold:
                unsure_tag = config.get_tag(asb.unsure_tag)
                if 'autotag' in config.sys.debug:
                    session.ui.debug(('Autotagging %s with %s (score=%.3f)'
                                      ) % (msg_mid, unsure_tag.name, score))
                keywords.add('%s:tag' % unsure_tag._key)
        except (KeyError, AttributeError, ValueError):
            pass

    return keywords


# We add a filter pre-hook with a high (late) priority.  Late priority to
# maximize the amount of data we are feeding to the classifier, but a
# pre-hook so normal filter rules will override the autotagging.
mailpile.plugins.register_filter_hook_post('90-autotag_sb', filter_hook)
