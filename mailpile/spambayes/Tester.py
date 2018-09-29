from spambayes.Options import options

class Test:
    # Pass a classifier instance (an instance of Bayes).
    # Loop:
    #     # Train the classifer with new ham and spam.
    #     train(ham, spam) # this implies reset_test_results
    #     Loop:
    #         Optional:
    #             # Possibly fiddle the classifier.
    #             set_classifier()
    #             # Forget smessages the classifier was trained on.
    #             untrain(ham, spam) # this implies reset_test_results
    #         Optional:
    #             reset_test_results()
    #         # Predict against (presumably new) examples.
    #         predict(ham, spam)
    #         Optional:
    #             suck out the results, via instance vrbls and
    #             false_negative_rate(), false_positive_rate(),
    #             false_negatives(), and false_positives()

    def __init__(self):
        self.reset_test_results()

    # Tell the tester which classifier to use.
    def set_classifier(self, classifier):
        self.classifier = classifier

    def reset_test_results(self):
        # The number of ham and spam instances tested.
        self.nham_tested = self.nspam_tested = 0

        # The number of test instances correctly and incorrectly classified.
        self.nham_right = 0
        self.nham_wrong = 0
        self.nham_unsure = 0
        self.nspam_right = 0
        self.nspam_wrong = 0
        self.nspam_unsure = 0

        # Lists of bad predictions.
        self.ham_wrong_examples = []    # False positives:  ham called spam.
        self.spam_wrong_examples = []   # False negatives:  spam called ham.
        self.unsure_examples = []       # ham and spam in middle ground

    # Train the classifier on streams of ham and spam.  Updates probabilities
    # before returning, and resets test results.
    def train(self, hamstream=None, spamstream=None):
        self.reset_test_results()
        learn = self.classifier.learn
        if hamstream is not None:
            for example in hamstream:
                learn(example, False)
        if spamstream is not None:
            for example in spamstream:
                learn(example, True)

    # Untrain the classifier on streams of ham and spam.  Updates
    # probabilities before returning, and resets test results.
    def untrain(self, hamstream=None, spamstream=None):
        self.reset_test_results()
        unlearn = self.classifier.unlearn
        if hamstream is not None:
            for example in hamstream:
                unlearn(example, False)
        if spamstream is not None:
            for example in spamstream:
                unlearn(example, True)

    # Run prediction on each sample in stream.  You're swearing that stream
    # is entirely composed of spam (is_spam True), or of ham (is_spam False).
    # Note that mispredictions are saved, and can be retrieved later via
    # false_negatives (spam mistakenly called ham) and false_positives (ham
    # mistakenly called spam).  For this reason, you may wish to wrap examples
    # in a little class that identifies the example in a useful way, and whose
    # __iter__ produces a token stream for the classifier.
    #
    # If specified, callback(msg, spam_probability) is called for each
    # msg in the stream, after the spam probability is computed.
    def predict(self, stream, is_spam, callback=None):
        guess = self.classifier.spamprob
        for example in stream:
            prob = guess(example)
            if callback:
                callback(example, prob)
            is_ham_guessed  = prob <  options["Categorization", "ham_cutoff"]
            is_spam_guessed = prob >= options["Categorization", "spam_cutoff"]
            if is_spam:
                self.nspam_tested += 1
                if is_spam_guessed:
                    self.nspam_right += 1
                elif is_ham_guessed:
                    self.nspam_wrong += 1
                    self.spam_wrong_examples.append(example)
                else:
                    self.nspam_unsure += 1
                    self.unsure_examples.append(example)
            else:
                self.nham_tested += 1
                if is_ham_guessed:
                    self.nham_right += 1
                elif is_spam_guessed:
                    self.nham_wrong += 1
                    self.ham_wrong_examples.append(example)
                else:
                    self.nham_unsure += 1
                    self.unsure_examples.append(example)

        assert (self.nham_right + self.nham_wrong + self.nham_unsure ==
                self.nham_tested)
        assert (self.nspam_right + self.nspam_wrong + self.nspam_unsure ==
                self.nspam_tested)

    def false_positive_rate(self):
        """Percentage of ham mistakenly identified as spam, in 0.0..100.0."""
        return self.nham_wrong * 1e2 / (self.nham_tested or 1)

    def false_negative_rate(self):
        """Percentage of spam mistakenly identified as ham, in 0.0..100.0."""
        return self.nspam_wrong * 1e2 / (self.nspam_tested or 1)

    def unsure_rate(self):
        return ((self.nham_unsure + self.nspam_unsure) * 1e2 /
                ((self.nham_tested + self.nspam_tested) or 1))

    def false_positives(self):
        return self.ham_wrong_examples

    def false_negatives(self):
        return self.spam_wrong_examples

    def unsures(self):
        return self.unsure_examples

class _Example:
    def __init__(self, name, words):
        self.name = name
        self.words = words
    def __iter__(self):
        return iter(self.words)

_easy_test = """
    >>> from spambayes.classifier import Bayes
    >>> from spambayes.Options import options
    >>> options["Categorization", "ham_cutoff"] = options["Categorization", "spam_cutoff"] = 0.5

    >>> good1 = _Example('', ['a', 'b', 'c'])
    >>> good2 = _Example('', ['a', 'b'])
    >>> bad1 = _Example('', ['c', 'd'])

    >>> t = Test()
    >>> t.set_classifier(Bayes())
    >>> t.train([good1, good2], [bad1])
    >>> t.predict([_Example('goodham', ['a', 'b']),
    ...            _Example('badham', ['d'])    # FP
    ...           ], False)
    >>> t.predict([_Example('goodspam', ['d']),
    ...            _Example('badspam1', ['a']), # FN
    ...            _Example('badspam2', ['a', 'b']),    # FN
    ...            _Example('badspam3', ['d', 'a', 'b'])    # FN
    ...           ], True)

    >>> t.nham_tested
    2
    >>> t.nham_right, t.nham_wrong
    (1, 1)
    >>> t.false_positive_rate()
    50.0
    >>> [e.name for e in t.false_positives()]
    ['badham']

    >>> t.nspam_tested
    4
    >>> t.nspam_right, t.nspam_wrong
    (1, 3)
    >>> t.false_negative_rate()
    75.0
    >>> [e.name for e in t.false_negatives()]
    ['badspam1', 'badspam2', 'badspam3']

    >>> [e.name for e in t.unsures()]
    []
    >>> t.unsure_rate()
    0.0
"""

__test__ = {'easy': _easy_test}

if __name__ == '__main__':
    import doctest
    doctest.testmod()
