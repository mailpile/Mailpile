# Add SpamBayes as an option to the autotagger. We like SpamBayes.
#
# We feed the classifier the same terms as go into the search engine,
# which should allow us to actually introspect a bit into the behavior
# of the classifier.

from spambayes.classifier import Classifier

import mailpile.plugins.autotag
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n


def _classifier(autotagger):
    if not hasattr(autotagger, 'spambayes'):
        autotagger.spambayes = Classifier()
    return autotagger.spambayes


class SpamBayesTagger(mailpile.plugins.autotag.Trainer):
    def should_tag(self, atagger, at_config, msg, keywords):
        score, evidence = _classifier(atagger).chi2_spamprob(keywords,
                                                             evidence=True)
        if score >= 1 - at_config.threshold:
            want = True
        elif score > at_config.threshold:
            want = None
        else:
            want = False
        return (want, score)


class SpamBayesTrainer(mailpile.plugins.autotag.Trainer):
    def learn(self, atagger, at_config, msg, keywords, should_tag):
        _classifier(atagger).learn(keywords, should_tag)

    def reset(self, atagger, at_config):
        atagger.spambayes = Classifier()


mailpile.plugins.autotag.TAGGERS['spambayes'] = SpamBayesTagger
mailpile.plugins.autotag.TRAINERS['spambayes'] = SpamBayesTrainer
