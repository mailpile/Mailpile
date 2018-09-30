"""Options

Abstract:

Options.options is a globally shared options object.
This object is initialised when the module is loaded: the envar
BAYESCUSTOMIZE is checked for a list of names, if nothing is found
then the local directory and the home directory are checked for a
file called bayescustomize.ini or .spambayesrc (respectively) and
the initial values are loaded from this.

The Option class is defined in OptionsClass.py - this module
is responsible only for instantiating and loading the globally
shared instance.

To Do:
 o Suggestions?
"""

from __future__ import print_function
import sys, os

try:
    _
except NameError:
    _ = lambda arg: arg

__all__ = ['options', '_']

# Grab the stuff from the core options class.
from mailpile.spambayes.OptionsClass import *

# A little magic.  We'd like to use ZODB as the default storage,
# because we've had so many problems with bsddb, and we'd like to swap
# to new ZODB problems <wink>.  However, apart from this, we only need
# a standard Python install - if the default was ZODB then we would
# need ZODB to be installed as well (which it will br for binary users,
# but might not be for source users).  So what we do is check whether
# ZODB is importable and if it is, default to that, and if not, default
# to dbm.  If ZODB is sometimes importable and sometimes not (e.g. you
# muck around with the PYTHONPATH), then this may not work well - the
# best idea would be to explicitly put the type in your configuration
# file.
try:
    import ZODB
except ImportError:
    DB_TYPE = "dbm", "hammie.db", "spambayes.messageinfo.db"
else:
    del ZODB
    DB_TYPE = "zodb", "hammie.fs", "messageinfo.fs"

# Format:
# defaults is a dictionary, where the keys are the section names
# each key maps to a tuple consisting of:
#   option name, display name, default,
#   doc string, possible values, restore on restore-to-defaults
# The display name and doc string should be enclosed in _() to allow
# i18n.  In a few cases, then possible values should also be enclosed
# in _().

defaults = {
  "Tokenizer" : (
    ("basic_header_tokenize", _("Basic header tokenising"), False,
     _("""If true, tokenizer.Tokenizer.tokenize_headers() will tokenize the
     contents of each header field just like the text of the message
     body, using the name of the header as a tag.  Tokens look like
     "header:word".  The basic approach is simple and effective, but also
     very sensitive to biases in the ham and spam collections.  For
     example, if the ham and spam were collected at different times,
     several headers with date/time information will become the best
     discriminators.  (Not just Date, but Received and X-From_.)"""),
     BOOLEAN, RESTORE),

    ("basic_header_tokenize_only", _("Only basic header tokenising"), False,
     _("""If true and basic_header_tokenize is also true, then
     basic_header_tokenize is the only action performed."""),
     BOOLEAN, RESTORE),

    ("basic_header_skip", _("Basic headers to skip"), ("received date x-.*",),
     _("""If basic_header_tokenize is true, then basic_header_skip is a set
     of headers that should be skipped."""),
     HEADER_NAME, RESTORE),

    ("check_octets", _("Check application/octet-stream sections"), False,
     _("""If true, the first few characters of application/octet-stream
     sections are used, undecoded.  What 'few' means is decided by
     octet_prefix_size."""),
     BOOLEAN, RESTORE),

    ("octet_prefix_size", _("Number of characters of octet stream to process"), 5,
     _("""The number of characters of the application/octet-stream sections
     to use, if check_octets is set to true."""),
     INTEGER, RESTORE),

    ("x-short_runs", _("Count runs of short 'words'"), False,
     _("""(EXPERIMENTAL) If true, generate tokens based on max number of
     short word runs. Short words are anything of length < the
     skip_max_word_size option.  Normally they are skipped, but one common
     spam technique spells words like 'V I A G RA'.
     """),
     BOOLEAN, RESTORE),

    ("x-lookup_ip", _("Generate IP address tokens from hostnames"), False,
     _("""(EXPERIMENTAL) Generate IP address tokens from hostnames.
     Requires PyDNS (http://pydns.sourceforge.net/)."""),
     BOOLEAN, RESTORE),

    ("lookup_ip_cache", _("x-lookup_ip cache file location"), "",
     _("""Tell SpamBayes where to cache IP address lookup information.
     Only comes into play if lookup_ip is enabled. The default
     (empty string) disables the file cache.  When caching is enabled,
     the cache file is stored using the same database type as the main
     token store (only dbm and zodb supported so far, zodb has problems,
     dbm is untested, hence the default)."""),
     PATH, RESTORE),

    ("image_size", _("Generate image size tokens"), False,
     _("""If true, generate tokens based on the sizes of
     embedded images."""),
     BOOLEAN, RESTORE),

    ("crack_images", _("Look inside images for text"), False,
     _("""If true, generate tokens based on the
     (hopefully) text content contained in any images in each message.
     The current support is minimal, relies on the installation of
     an OCR 'engine' (see ocr_engine.)"""),
     BOOLEAN, RESTORE),

    ("ocr_engine", _("OCR engine to use"), "",
     _("""The name of the OCR engine to use.  If empty, all
     supported engines will be checked to see if they are installed.
     Engines currently supported include ocrad
     (http://www.gnu.org/software/ocrad/ocrad.html) and gocr
     (http://jocr.sourceforge.net/download.html) and they require the
     appropriate executable be installed in either your PATH, or in the
     main spambayes directory."""),
     HEADER_VALUE, RESTORE),

    ("crack_image_cache", _("Cache to speed up ocr."), "",
     _("""If non-empty, names a file from which to read cached ocr info
     at start and to which to save that info at exit."""),
     PATH, RESTORE),

    ("ocrad_scale", _("Scale factor to use with ocrad."), 2,
     _("""Specifies the scale factor to apply when running ocrad.  While
     you can specify a negative scale it probably won't help.  Scaling up
     by a factor of 2 or 3 seems to work well for the sort of spam images
     encountered by SpamBayes."""),
     INTEGER, RESTORE),

    ("ocrad_charset", _("Charset to apply with ocrad."), "ascii",
     _("""Specifies the charset to use when running ocrad.  Valid values
     are 'ascii', 'iso-8859-9' and 'iso-8859-15'."""),
     OCRAD_CHARSET, RESTORE),

    ("max_image_size", _("Max image size to try OCR-ing"), 100000,
     _("""When crack_images is enabled, this specifies the largest
     image to try OCR on."""),
     INTEGER, RESTORE),

    ("count_all_header_lines", _("Count all header lines"), False,
     _("""Generate tokens just counting the number of instances of each kind
     of header line, in a case-sensitive way.

     Depending on data collection, some headers are not safe to count.
     For example, if ham is collected from a mailing list but spam from
     your regular inbox traffic, the presence of a header like List-Info
     will be a very strong ham clue, but a bogus one.  In that case, set
     count_all_header_lines to False, and adjust safe_headers instead."""),
     BOOLEAN, RESTORE),

    ("record_header_absence", _("Record header absence"), False,
     _("""When True, generate a "noheader:HEADERNAME" token for each header
     in safe_headers (below) that *doesn't* appear in the headers.  This
     helped in various of Tim's python.org tests, but appeared to hurt a
     little in Anthony Baxter's tests."""),
     BOOLEAN, RESTORE),

    ("safe_headers", _("Safe headers"), ("abuse-reports-to", "date", "errors-to",
                                      "from", "importance", "in-reply-to",
                                      "message-id", "mime-version",
                                      "organization", "received",
                                      "reply-to", "return-path", "subject",
                                      "to", "user-agent", "x-abuse-info",
                                      "x-complaints-to", "x-face"),
     _("""Like count_all_header_lines, but restricted to headers in this list.
     safe_headers is ignored when count_all_header_lines is true, unless
     record_header_absence is also true."""),
     HEADER_NAME, RESTORE),

    ("mine_received_headers", _("Mine the received headers"), False,
     _("""A lot of clues can be gotten from IP addresses and names in
     Received: headers.  This can give spectacular results for bogus
     reasons if your corpora are from different sources."""),
     BOOLEAN, RESTORE),

    ("x-mine_nntp_headers", _("Mine NNTP-Posting-Host headers"), False,
     _("""Usenet is host to a lot of spam.  Usenet/Mailing list gateways
     can let it leak across.  Similar to mining received headers, we pick
     apart the IP address or host name in this header for clues."""),
     BOOLEAN, RESTORE),

    ("address_headers", _("Address headers to mine"), ("from", "to", "cc",
                                                       "sender", "reply-to"),
     _("""Mine the following address headers. If you have mixed source
     corpuses (as opposed to a mixed sauce walrus, which is delicious!)
     then you probably don't want to use 'to' or 'cc') Address headers will
     be decoded, and will generate charset tokens as well as the real
     address.  Others to consider: errors-to, ..."""),
     HEADER_NAME, RESTORE),

    ("generate_long_skips", _("Generate long skips"), True,
     _("""If legitimate mail contains things that look like text to the
     tokenizer and turning turning off this option helps (perhaps binary
     attachments get 'defanged' by something upstream from this operation
     and thus look like text), this may help, and should be an alert that
     perhaps the tokenizer is broken."""),
     BOOLEAN, RESTORE),

    ("summarize_email_prefixes", _("Summarise email prefixes"), False,
     _("""Try to capitalize on mail sent to multiple similar addresses."""),
     BOOLEAN, RESTORE),

    ("summarize_email_suffixes", _("Summarise email suffixes"), False,
     _("""Try to capitalize on mail sent to multiple similar addresses."""),
     BOOLEAN, RESTORE),

    ("skip_max_word_size", _("Long skip trigger length"), 12,
     _("""Length of words that triggers 'long skips'. Longer than this
     triggers a skip."""),
     INTEGER, RESTORE),

    ("x-pick_apart_urls", _("Extract clues about url structure"), False,
     _("""(EXPERIMENTAL) Note whether url contains non-standard port or
     user/password elements."""),
     BOOLEAN, RESTORE),

    ("x-fancy_url_recognition", _("Extract URLs without http:// prefix"), False,
     _("""(EXPERIMENTAL) Recognize 'www.python.org' or ftp.python.org as URLs
     instead of just long words."""),
     BOOLEAN, RESTORE),

    ("replace_nonascii_chars", _("Replace non-ascii characters"), False,
     _("""If true, replace high-bit characters (ord(c) >= 128) and control
     characters with question marks.  This allows non-ASCII character
     strings to be identified with little training and small database
     burden.  It's appropriate only if your ham is plain 7-bit ASCII, or
     nearly so, so that the mere presence of non-ASCII character strings is
     known in advance to be a strong spam indicator."""),
     BOOLEAN, RESTORE),

    ("x-search_for_habeas_headers", _("Search for Habeas Headers"), False,
     _("""(EXPERIMENTAL) If true, search for the habeas headers (see
     http://www.habeas.com). If they are present and correct, this should
     be a strong ham sign, if they are present and incorrect, this should
     be a strong spam sign."""),
     BOOLEAN, RESTORE),

    ("x-reduce_habeas_headers", _("Reduce Habeas Header Tokens to Single"), False,
     _("""(EXPERIMENTAL) If SpamBayes is set to search for the Habeas
     headers, nine tokens are generated for messages with habeas headers.
     This should be fine, since messages with the headers should either be
     ham, or result in FN so that we can send them to habeas so they can
     be sued.  However, to reduce the strength of habeas headers, we offer
     the ability to reduce the nine tokens to one. (This option has no
     effect if 'Search for Habeas Headers' is False)"""),
     BOOLEAN, RESTORE),
  ),

  # These options control how a message is categorized
  "Categorization" : (
    # spam_cutoff and ham_cutoff are used in Python slice sense:
    #    A msg is considered    ham if its score is in 0:ham_cutoff
    #    A msg is considered unsure if its score is in ham_cutoff:spam_cutoff
    #    A msg is considered   spam if its score is in spam_cutoff:
    #
    # So it's unsure iff  ham_cutoff <= score < spam_cutoff.
    # For a binary classifier, make ham_cutoff == spam_cutoff.
    # ham_cutoff > spam_cutoff doesn't make sense.
    #
    # The defaults here (.2 and .9) may be appropriate for the default chi-
    # combining scheme.  Cutoffs for chi-combining typically aren't touchy,
    # provided you're willing to settle for "really good" instead of "optimal".
    # Tim found that .3 and .8 worked very well for well-trained systems on
    # his personal email, and his large comp.lang.python test.  If just
    # beginning training, or extremely fearful of mistakes, 0.05 and 0.95 may
    # be more appropriate for you.
    #
    # Picking good values for gary-combining is much harder, and appears to be
    # corpus-dependent, and within a single corpus dependent on how much
    # training has been done.  Values from 0.50 thru the low 0.60's have been
    # reported to work best by various testers on their data.
    ("ham_cutoff", _("Ham cutoff"), 0.20,
     _("""Spambayes gives each email message a spam probability between
     0 and 1. Emails below the Ham Cutoff probability are classified
     as Ham. Larger values will result in more messages being
     classified as ham, but with less certainty that all of them
     actually are ham. This value should be between 0 and 1,
     and should be smaller than the Spam Cutoff."""),
     REAL, RESTORE),

    ("spam_cutoff", _("Spam cutoff"), 0.90,
     _("""Emails with a spam probability above the Spam Cutoff are
     classified as Spam - just like the Ham Cutoff but at the other
     end of the scale.  Messages that fall between the two values
     are classified as Unsure."""),
     REAL, RESTORE),
  ),

  # These control various displays in class TestDriver.Driver, and
  # Tester.Test.
  "TestDriver" : (
    ("nbuckets", _("Number of buckets"), 200,
     _("""Number of buckets in histograms."""),
     INTEGER, RESTORE),

    ("show_histograms", _("Show histograms"), True,
     _(""""""),
     BOOLEAN, RESTORE),

    ("compute_best_cutoffs_from_histograms", _("Compute best cutoffs from histograms"), True,
     _("""After the display of a ham+spam histogram pair, you can get a
     listing of all the cutoff values (coinciding with histogram bucket
     boundaries) that minimize:
         best_cutoff_fp_weight * (# false positives) +
         best_cutoff_fn_weight * (# false negatives) +
         best_cutoff_unsure_weight * (# unsure msgs)

     This displays two cutoffs:  hamc and spamc, where
        0.0 <= hamc <= spamc <= 1.0

     The idea is that if something scores < hamc, it's called ham; if
     something scores >= spamc, it's called spam; and everything else is
     called 'I am not sure' -- the middle ground.

     Note:  You may wish to increase nbuckets, to give this scheme more cutoff
     values to analyze."""),
     BOOLEAN, RESTORE),

    ("best_cutoff_fp_weight", _("Best cutoff false positive weight"), 10.00,
     _(""""""),
     REAL, RESTORE),

    ("best_cutoff_fn_weight", _("Best cutoff false negative weight"), 1.00,
     _(""""""),
     REAL, RESTORE),

    ("best_cutoff_unsure_weight", _("Best cutoff unsure weight"), 0.20,
     _(""""""),
     REAL, RESTORE),

    ("percentiles", _("Percentiles"), (5, 25, 75, 95),
     _("""Histogram analysis also displays percentiles.  For each percentile
     p in the list, the score S such that p% of all scores are <= S is
     given. Note that percentile 50 is the median, and is displayed (along
     with the min score and max score) independent of this option."""),
     INTEGER, RESTORE),

    ("show_spam_lo", _(""), 1.0,
     _("""Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything."""),
     REAL, RESTORE),

    ("show_spam_hi", _(""), 0.0,
     _("""Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything."""),
     REAL, RESTORE),

    ("show_ham_lo", _(""), 1.0,
     _("""Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything."""),
     REAL, RESTORE),

    ("show_ham_hi", _(""), 0.0,
     _("""Display spam when show_spam_lo <= spamprob <= show_spam_hi and
     likewise for ham.  The defaults here do not show anything."""),
     REAL, RESTORE),

    ("show_false_positives", _("Show false positives"), True,
     _(""""""),
     BOOLEAN, RESTORE),

    ("show_false_negatives", _("Show false negatives"), False,
     _(""""""),
     BOOLEAN, RESTORE),

    ("show_unsure", _("Show unsure"), False,
     _(""""""),
     BOOLEAN, RESTORE),

    ("show_charlimit", _("Show character limit"), 3000,
     _("""The maximum # of characters to display for a msg displayed due to
     the show_xyz options above."""),
     INTEGER, RESTORE),

    ("save_trained_pickles", _("Save trained pickles"), False,
     _("""If save_trained_pickles is true, Driver.train() saves a binary
     pickle of the classifier after training.  The file basename is given
     by pickle_basename, the extension is .pik, and increasing integers are
     appended to pickle_basename.  By default (if save_trained_pickles is
     true), the filenames are class1.pik, class2.pik, ...  If a file of
     that name already exists, it is overwritten.  pickle_basename is
     ignored when save_trained_pickles is false."""),
     BOOLEAN, RESTORE),

    ("pickle_basename", _("Pickle basename"), "class",
     _(""""""),
     r"[\w]+", RESTORE),

    ("save_histogram_pickles", _("Save histogram pickles"), False,
     _("""If save_histogram_pickles is true, Driver.train() saves a binary
     pickle of the spam and ham histogram for "all test runs". The file
     basename is given by pickle_basename, the suffix _spamhist.pik
     or _hamhist.pik is appended  to the basename."""),
     BOOLEAN, RESTORE),

    ("spam_directories", _("Spam directories"), "Data/Spam/Set%d",
     _("""default locations for timcv and timtest - these get the set number
     interpolated."""),
     VARIABLE_PATH, RESTORE),

    ("ham_directories", _("Ham directories"), "Data/Ham/Set%d",
     _("""default locations for timcv and timtest - these get the set number
     interpolated."""),
     VARIABLE_PATH, RESTORE),
  ),

  "CV Driver": (
    ("build_each_classifier_from_scratch", _("Build each classifier from scratch"), False,
     _("""A cross-validation driver takes N ham+spam sets, and builds N
     classifiers, training each on N-1 sets, and the predicting against the
     set not trained on.  By default, it does this in a clever way,
     learning *and* unlearning sets as it goes along, so that it never
     needs to train on N-1 sets in one gulp after the first time.  Setting
     this option true forces ''one gulp from-scratch'' training every time.
     There used to be a set of combining schemes that needed this, but now
     it is just in case you are paranoid <wink>."""),
     BOOLEAN, RESTORE),
  ),

  "Classifier": (
    ("max_discriminators", _("Maximum number of extreme words"), 150,
     _("""The maximum number of extreme words to look at in a message, where
     "extreme" means with spam probability farthest away from 0.5.  150
     appears to work well across all corpora tested."""),
     INTEGER, RESTORE),

    ("unknown_word_prob", _("Unknown word probability"), 0.5,
     _("""These two control the prior assumption about word probabilities.
     unknown_word_prob is essentially the probability given to a word that
     has never been seen before.  Nobody has reported an improvement via
     moving it away from 1/2, although Tim has measured a mean spamprob of
     a bit over 0.5 (0.51-0.55) in 3 well-trained classifiers."""),
     REAL, RESTORE),

    ("unknown_word_strength", _("Unknown word strength"), 0.45,
     _("""This adjusts how much weight to give the prior
     assumption relative to the probabilities estimated by counting.  At 0,
     the counting estimates are believed 100%, even to the extent of
     assigning certainty (0 or 1) to a word that has appeared in only ham
     or only spam.  This is a disaster.

     As unknown_word_strength tends toward infinity, all probabilities
     tend toward unknown_word_prob.  All reports were that a value near 0.4
     worked best, so this does not seem to be corpus-dependent."""),
     REAL, RESTORE),

    ("minimum_prob_strength", _("Minimum probability strength"), 0.1,
     _("""When scoring a message, ignore all words with
     abs(word.spamprob - 0.5) < minimum_prob_strength.
     This may be a hack, but it has proved to reduce error rates in many
     tests.  0.1 appeared to work well across all corpora."""),
     REAL, RESTORE),

    ("use_chi_squared_combining", _("Use chi-squared combining"), True,
     _("""For vectors of random, uniformly distributed probabilities,
     -2*sum(ln(p_i)) follows the chi-squared distribution with 2*n degrees
     of freedom.  This is the "provably most-sensitive" test the original
     scheme was monotonic with.  Getting closer to the theoretical basis
     appears to give an excellent combining method, usually very extreme in
     its judgment, yet finding a tiny (in # of msgs, spread across a huge
     range of scores) middle ground where lots of the mistakes live.  This
     is the best method so far. One systematic benefit is is immunity to
     "cancellation disease". One systematic drawback is sensitivity to
     *any* deviation from a uniform distribution, regardless of whether
     actually evidence of ham or spam. Rob Hooft alleviated that by
     combining the final S and H measures via (S-H+1)/2 instead of via
     S/(S+H)). In practice, it appears that setting ham_cutoff=0.05, and
     spam_cutoff=0.95, does well across test sets; while these cutoffs are
     rarely optimal, they get close to optimal.  With more training data,
     Tim has had good luck with ham_cutoff=0.30 and spam_cutoff=0.80 across
     three test data sets (original c.l.p data, his own email, and newer
     general python.org traffic)."""),
     BOOLEAN, RESTORE),

    ("use_bigrams", _("Use mixed uni/bi-grams scheme"), False,
     _("""Generate both unigrams (words) and bigrams (pairs of
     words). However, extending an idea originally from Gary Robinson, the
     message is 'tiled' into non-overlapping unigrams and bigrams,
     approximating the strongest outcome over all possible tilings.

     Note that to really test this option you need to retrain with it on,
     so that your database includes the bigrams - if you subsequently turn
     it off, these tokens will have no effect.  This option will at least
     double your database size given the same training data, and will
     probably at least triple it.

     You may also wish to increase the max_discriminators (maximum number
     of extreme words) option if you enable this option, perhaps doubling or
     quadrupling it.  It's not yet clear.  Bigrams create many more hapaxes,
     and that seems to increase the brittleness of minimalist training
     regimes; increasing max_discriminators may help to soften that effect.
     OTOH, max_discriminators defaults to 150 in part because that makes it
     easy to prove that the chi-squared math is immune from numeric
     problems.  Increase it too much, and insane results will eventually
     result (including fatal floating-point exceptions on some boxes).

     This option is experimental, and may be removed in a future release.
     We would appreciate feedback about it if you use it - email
     spambayes@python.org with your comments and results.
     """),
     BOOLEAN, RESTORE),
  ),

  "Hammie": (
    ("train_on_filter", _("Train when filtering"), False,
     _("""Train when filtering?  After filtering a message, hammie can then
     train itself on the judgement (ham or spam).  This can speed things up
     with a procmail-based solution.  If you do enable this, please make
     sure to retrain any mistakes.  Otherwise, your word database will
     slowly become useless.  Note that this option is only used by
     sb_filter, and will have no effect on sb_server's POP3 proxy, or
     the IMAP filter."""),
     BOOLEAN, RESTORE),
  ),

  # These options control where Spambayes data will be stored, and in
  # what form.  They are used by many Spambayes applications (including
  # pop3proxy, smtpproxy, imapfilter and hammie), and mean that data
  # (such as the message database) is shared between the applications.
  # If this is not the desired behaviour, you must have a different
  # value for each of these options in a configuration file that gets
  # loaded by the appropriate application only.
  "Storage" : (
    ("persistent_use_database", _("Database backend"), DB_TYPE[0],
     _("""SpamBayes can use either a ZODB or dbm database (quick to score
     one message) or a pickle (quick to train on huge amounts of messages).
     There is also (experimental) ability to use a mySQL or PostgresSQL
     database."""),
     ("zeo", "zodb", "cdb", "mysql", "pgsql", "dbm", "pickle"), RESTORE),

    ("persistent_storage_file", _("Storage file name"), DB_TYPE[1],
     _("""Spambayes builds a database of information that it gathers
     from incoming emails and from you, the user, to get better and
     better at classifying your email.  This option specifies the
     name of the database file.  If you don't give a full pathname,
     the name will be taken to be relative to the location of the
     most recent configuration file loaded."""),
     FILE_WITH_PATH, DO_NOT_RESTORE),

    ("messageinfo_storage_file", _("Message information file name"), DB_TYPE[2],
     _("""Spambayes builds a database of information about messages
     that it has already seen and trained or classified.  This
     database is used to ensure that these messages are not retrained
     or reclassified (unless specifically requested to).  This option
     specifies the name of the database file.  If you don't give a
     full pathname, the name will be taken to be relative to the location
     of the most recent configuration file loaded."""),
     FILE_WITH_PATH, DO_NOT_RESTORE),

    ("cache_use_gzip", _("Use gzip"), False,
     _("""Use gzip to compress the cache."""),
     BOOLEAN, RESTORE),

    ("cache_expiry_days", _("Days before cached messages expire"), 7,
     _("""Messages will be expired from the cache after this many days.
     After this time, you will no longer be able to train on these messages
     (note this does not affect the copy of the message that you have in
     your mail client)."""),
     INTEGER, RESTORE),

    ("spam_cache", _("Spam cache directory"), "pop3proxy-spam-cache",
     _("""Directory that SpamBayes should cache spam in.  If this does
     not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("ham_cache", _("Ham cache directory"), "pop3proxy-ham-cache",
     _("""Directory that SpamBayes should cache ham in.  If this does
     not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("unknown_cache", _("Unknown cache directory"), "pop3proxy-unknown-cache",
     _("""Directory that SpamBayes should cache unclassified messages in.
     If this does not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("core_spam_cache", _("Spam cache directory"), "core-spam-cache",
     _("""Directory that SpamBayes should cache spam in.  If this does
     not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("core_ham_cache", _("Ham cache directory"), "core-ham-cache",
     _("""Directory that SpamBayes should cache ham in.  If this does
     not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("core_unknown_cache", _("Unknown cache directory"), "core-unknown-cache",
     _("""Directory that SpamBayes should cache unclassified messages in.
     If this does not exist, it will be created."""),
     PATH, DO_NOT_RESTORE),

    ("cache_messages", _("Cache messages"), True,
     _("""You can disable the pop3proxy caching of messages.  This
     will make the proxy a bit faster, and make it use less space
     on your hard drive.  The proxy uses its cache for reviewing
     and training of messages, so if you disable caching you won't
     be able to do further training unless you re-enable it.
     Thus, you should only turn caching off when you are satisfied
     with the filtering that Spambayes is doing for you."""),
     BOOLEAN, RESTORE),

    ("no_cache_bulk_ham", _("Suppress caching of bulk ham"), False,
     _("""Where message caching is enabled, this option suppresses caching
     of messages which are classified as ham and marked as
     'Precedence: bulk' or 'Precedence: list'.  If you subscribe to a
     high-volume mailing list then your 'Review messages' page can be
     overwhelmed with list messages, making training a pain.  Once you've
     trained Spambayes on enough list traffic, you can use this option
     to prevent that traffic showing up in 'Review messages'."""),
     BOOLEAN, RESTORE),

    ("no_cache_large_messages", _("Maximum size of cached messages"), 0,
     _("""Where message caching is enabled, this option suppresses caching
     of messages which are larger than this value (measured in bytes).
     If you receive a lot of messages that include large attachments
     (and are correctly classified), you may not wish to cache these.
     If you set this to zero (0), then this option will have no effect."""),
     INTEGER, RESTORE),
  ),

  # These options control the various headers that some Spambayes
  # applications add to incoming mail, including imapfilter, pop3proxy,
  # and hammie.
  "Headers" : (
    # The name of the header that hammie, pop3proxy, and any other spambayes
    # software, adds to emails in filter mode.  This will definately contain
    # the "classification" of the mail, and may also (i.e. with hammie)
    # contain the score
    ("classification_header_name", _("Classification header name"), "X-Spambayes-Classification",
     _("""Spambayes classifies each message by inserting a new header into
     the message.  This header can then be used by your email client
     (provided your client supports filtering) to move spam into a
     separate folder (recommended), delete it (not recommended), etc.
     This option specifies the name of the header that Spambayes inserts.
     The default value should work just fine, but you may change it to
     anything that you wish."""),
     HEADER_NAME, RESTORE),

    # The three disposition names are added to the header as the following
    # three words:
    ("header_spam_string", _("Spam disposition name"), _("spam"),
     _("""The header that Spambayes inserts into each email has a name,
     (Classification header name, above), and a value.  If the classifier
     determines that this email is probably spam, it places a header named
     as above with a value as specified by this string.  The default
     value should work just fine, but you may change it to anything
     that you wish."""),
     HEADER_VALUE, RESTORE),

    ("header_ham_string", _("Ham disposition name"), _("ham"),
     _("""As for Spam Designation, but for emails classified as Ham."""),
     HEADER_VALUE, RESTORE),

    ("header_unsure_string", _("Unsure disposition name"), _("unsure"),
     _("""As for Spam/Ham Designation, but for emails which the
     classifer wasn't sure about (ie. the spam probability fell between
     the Ham and Spam Cutoffs).  Emails that have this classification
     should always be the subject of training."""),
     HEADER_VALUE, RESTORE),

    ("header_score_digits", _("Accuracy of reported score"), 2,
     _("""Accuracy of the score in the header in decimal digits."""),
     INTEGER, RESTORE),

    ("header_score_logarithm", _("Augment score with logarithm"), False,
     _("""Set this option to augment scores of 1.00 or 0.00 by a
     logarithmic "one-ness" or "zero-ness" score (basically it shows the
     "number of zeros" or "number of nines" next to the score value)."""),
     BOOLEAN, RESTORE),

    ("include_score", _("Add probability (score) header"), False,
     _("""You can have Spambayes insert a header with the calculated spam
     probability into each mail.  If you can view headers with your
     mailer, then you can see this information, which can be interesting
     and even instructive if you're a serious SpamBayes junkie."""),
     BOOLEAN, RESTORE),

    ("score_header_name", _("Probability (score) header name"), "X-Spambayes-Spam-Probability",
     _(""""""),
     HEADER_NAME, RESTORE),

    ("include_thermostat", _("Add level header"), False,
     _("""You can have spambayes insert a header with the calculated spam
     probability, expressed as a number of '*'s, into each mail (the more
     '*'s, the higher the probability it is spam). If your mailer
     supports it, you can use this information to fine tune your
     classification of ham/spam, ignoring the classification given."""),
     BOOLEAN, RESTORE),

    ("thermostat_header_name", _("Level header name"), "X-Spambayes-Level",
     _(""""""),
     HEADER_NAME, RESTORE),

    ("include_evidence", _("Add evidence header"), False,
     _("""You can have spambayes insert a header into mail, with the
     evidence that it used to classify that message (a collection of
     words with ham and spam probabilities).  If you can view headers
     with your mailer, then this may give you some insight as to why
     a particular message was scored in a particular way."""),
     BOOLEAN, RESTORE),

    ("evidence_header_name", _("Evidence header name"), "X-Spambayes-Evidence",
     _(""""""),
     HEADER_NAME, RESTORE),

    ("mailid_header_name", _("Spambayes id header name"), "X-Spambayes-MailId",
     _(""""""),
     HEADER_NAME, RESTORE),

    ("include_trained", _("Add trained header"), True,
     _("""sb_mboxtrain.py and sb_filter.py can add a header that details
     how a message was trained, which lets you keep track of it, and
     appropriately re-train messages.  However, if you would rather
     mboxtrain/sb_filter didn't rewrite the message files, you can disable
     this option."""),
     BOOLEAN, RESTORE),

    ("trained_header_name", _("Trained header name"), "X-Spambayes-Trained",
     _("""When training on a message, the name of the header to add with how
     it was trained"""),
     HEADER_NAME, RESTORE),

    ("clue_mailheader_cutoff", _("Debug header cutoff"), 0.5,
     _("""The range of clues that are added to the "debug" header in the
     E-mail. All clues that have their probability smaller than this number,
     or larger than one minus this number are added to the header such that
     you can see why spambayes thinks this is ham/spam or why it is unsure.
     The default is to show all clues, but you can reduce that by setting
     showclue to a lower value, such as 0.1"""),
     REAL, RESTORE),

    ("add_unique_id", _("Add unique spambayes id"), True,
     _("""If you wish to be able to find a specific message (via the 'find'
     box on the home page), or use the SMTP proxy to train using cached
     messages, you will need to know the unique id of each message.  This
     option adds this information to a header added to each message."""),
     BOOLEAN, RESTORE),

    ("notate_to", _("Notate to"), (),
     _("""Some email clients (Outlook Express, for example) can only set up
     filtering rules on a limited set of headers.  These clients cannot
     test for the existence/value of an arbitrary header and filter mail
     based on that information.  To accommodate these kind of mail clients,
     you can add "spam", "ham", or "unsure" to the recipient list.  A
     filter rule can then use this to see if one of these words (followed
     by a comma) is in the recipient list, and route the mail to an
     appropriate folder, or take whatever other action is supported and
     appropriate for the mail classification.

     As it interferes with replying, you may only wish to do this for
     spam messages; simply tick the boxes of the classifications take
     should be identified in this fashion."""),
     ((), _("ham"), _("spam"), _("unsure")), RESTORE),

    ("notate_subject", _("Classify in subject: header"), (),
     _("""This option will add the same information as 'Notate To',
     but to the start of the mail subject line."""),
     ((), _("ham"), _("spam"), _("unsure")), RESTORE),
  ),

  # pop3proxy settings: The only mandatory option is pop3proxy_servers, eg.
  # "pop3.my-isp.com:110", or a comma-separated list of those.  The ":110"
  # is optional.  If you specify more than one server in pop3proxy_servers,
  # you must specify the same number of ports in pop3proxy_ports.
  "pop3proxy" : (
    ("remote_servers", _("Remote Servers"), (),
     _("""\
     The SpamBayes POP3 proxy intercepts incoming email and classifies it
     before sending it on to your email client.  You need to specify which
     POP3 server(s) and port(s) you wish it to connect to - a POP3 server
     address typically looks like 'pop3.myisp.net:110' where
     'pop3.myisp.net' is the name of the computer where the POP3 server runs
     and '110' is the port on which the POP3 server listens.  The other port
     you might find is '995', which is used for secure POP3.  If you use
     more than one server, simply separate their names with commas.  For
     example:  'pop3.myisp.net:110,pop.gmail.com:995'.  You can get
     these server names and port numbers from your existing email
     configuration, or from your ISP or system administrator.  If you are
     using Web-based email, you can't use the SpamBayes POP3 proxy (sorry!).
     In your email client's configuration, where you would normally put your
     POP3 server address, you should now put the address of the machine
     running SpamBayes.
"""),
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", _("SpamBayes Ports"), (),
     _("""\
     Each monitored POP3 server must be assigned to a different port in the
     SpamBayes POP3 proxy.  You need to configure your email client to
     connect to this port instead of the actual remote POP3 server.  If you
     don't know what port to use, try 8110 and go up from there.  If you
     have two servers, your list of listen ports might then be '8110,8111'.
"""),
     SERVER, DO_NOT_RESTORE),

    ("allow_remote_connections", _("Allowed remote POP3 connections"), "localhost",
     _("""Enter a list of trusted IPs, separated by commas. Remote POP
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address."""),
     IP_LIST, RESTORE),

    ("retrieval_timeout", _("Retrieval timeout"), 30,
     _("""When proxying messages, time out after this length of time if
     all the headers have been received.  The rest of the mesasge will
     proxy straight through.  Some clients have a short timeout period,
     and will give up on waiting for the message if this is too long.
     Note that the shorter this is, the less of long messages will be
     used for classifications (i.e. results may be effected)."""),
     REAL, RESTORE),

    ("use_ssl", "Connect via a secure socket layer", False,
     """Use SSL to connect to the server. This allows spambayes to connect
     without sending data in plain text.

     Note that this does not check the server certificate at this point in
     time.""",
     (False, True, "automatic"), DO_NOT_RESTORE),
  ),

  "smtpproxy" : (
    ("remote_servers", _("Remote Servers"), (),
     _("""Use of the SMTP proxy is optional - if you would rather just train
     via the web interface, or the pop3dnd or mboxtrain scripts, then you
     can safely leave this option blank.  The Spambayes SMTP proxy
     intercepts outgoing email - if you forward mail to one of the
     addresses below, it is examined for an id and the message
     corresponding to that id is trained as ham/spam.  All other mail is
     sent along to your outgoing mail server.  You need to specify which
     SMTP server(s) you wish it to intercept - a SMTP server address
     typically looks like "smtp.myisp.net".  If you use more than one
     server, simply separate their names with commas.  You can get these
     server names from your existing email configuration, or from your ISP
     or system administrator.  If you are using Web-based email, you can't
     use the Spambayes SMTP proxy (sorry!).  In your email client's
     configuration, where you would normally put your SMTP server address,
     you should now put the address of the machine running SpamBayes."""),
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", _("SpamBayes Ports"), (),
     _("""Each SMTP server that is being monitored must be assigned to a
     'port' in the Spambayes SMTP proxy.  This port must be different for
     each monitored server, and there must be a port for
     each monitored server.  Again, you need to configure your email
     client to use this port.  If there are multiple servers, you must
     specify the same number of ports as servers, separated by commas."""),
     SERVER, DO_NOT_RESTORE),

    ("allow_remote_connections", _("Allowed remote SMTP connections"), "localhost",
     _("""Enter a list of trusted IPs, separated by commas. Remote SMTP
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address.  Note that you can unwittingly
     turn a SMTP server into an open proxy if you open this up, as
     connections to the server will appear to be from your machine, even
     if they are from a remote machine *through* your machine, to the
     server.  We do not recommend opening this up fully (i.e. using '*').
     """),
     IP_LIST, RESTORE),

    ("ham_address", _("Train as ham address"), "spambayes_ham@localhost",
     _("""When a message is received that you wish to train on (for example,
     one that was incorrectly classified), you need to forward or bounce
     it to one of two special addresses so that the SMTP proxy can identify
     it.  If you wish to train it as ham, forward or bounce it to this
     address.  You will want to use an address that is not
     a valid email address, like ham@nowhere.nothing."""),
     EMAIL_ADDRESS, RESTORE),

    ("spam_address", _("Train as spam address"), "spambayes_spam@localhost",
     _("""As with Ham Address above, but the address that you need to forward
     or bounce mail that you wish to train as spam.  You will want to use
     an address that is not a valid email address, like
     spam@nowhere.nothing."""),
     EMAIL_ADDRESS, RESTORE),

    ("use_cached_message", _("Lookup message in cache"), False,
     _("""If this option is set, then the smtpproxy will attempt to
     look up the messages sent to it (for training) in the POP3 proxy cache
     or IMAP filter folders, and use that message as the training data.
     This avoids any problems where your mail client might change the
     message when forwarding, contaminating your training data.  If you can
     be sure that this won't occur, then the id-lookup can be avoided.

     Note that Outlook Express users cannot use the lookup option (because
     of the way messages are forwarded), and so if they wish to use the
     SMTP proxy they must enable this option (but as messages are altered,
     may not get the best results, and this is not recommended)."""),
     BOOLEAN, RESTORE),
  ),

  # imap4proxy settings: The only mandatory option is imap4proxy_servers, eg.
  # "imap4.my-isp.com:143", or a comma-separated list of those.  The ":143"
  # is optional.  If you specify more than one server in imap4proxy_servers,
  # you must specify the same number of ports in imap4proxy_ports.
  "imap4proxy" : (
    ("remote_servers", _("Remote Servers"), (),
     _("""The SpamBayes IMAP4 proxy intercepts incoming email and classifies
     it before sending it on to your email client.  You need to specify
     which IMAP4 server(s) you wish it to intercept - a IMAP4 server
     address typically looks like "mail.myisp.net".  If you use more than
     one server, simply separate their names with commas.  You can get
     these server names from your existing email configuration, or from
     your ISP or system administrator.  If you are using Web-based email,
     you can't use the SpamBayes IMAP4 proxy (sorry!).  In your email
     client's configuration, where you would normally put your IMAP4 server
     address, you should now put the address of the machine running
     SpamBayes."""),
     SERVER, DO_NOT_RESTORE),

    ("listen_ports", _("SpamBayes Ports"), (),
     _("""Each IMAP4 server that is being monitored must be assigned to a
     'port' in the SpamBayes IMAP4 proxy.  This port must be different for
     each monitored server, and there must be a port for each monitored
     server.  Again, you need to configure your email client to use this
     port.  If there are multiple servers, you must specify the same number
     of ports as servers, separated by commas. If you don't know what to
     use here, and you only have one server, try 143, or if that doesn't
     work, try 8143."""),
     SERVER, DO_NOT_RESTORE),

    ("allow_remote_connections", _("Allowed remote IMAP4 connections"), "localhost",
     _("""Enter a list of trusted IPs, separated by commas. Remote IMAP
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address."""),
     IP_LIST, RESTORE),

    ("use_ssl", "Connect via a secure socket layer", False,
     """Use SSL to connect to the server. This allows spambayes to connect
     without sending data in plain text.

     Note that this does not check the server certificate at this point in
     time.""",
     (False, True, "automatic"), DO_NOT_RESTORE),
  ),

  "html_ui" : (
    ("port", _("Port"), 8880,
     _(""""""),
     PORT, RESTORE),

    ("launch_browser", _("Launch browser"), False,
     _("""If this option is set, then whenever sb_server or sb_imapfilter is
     started the default web browser will be opened to the main web
     interface page.  Use of the -b switch when starting from the command
     line overrides this option."""),
     BOOLEAN, RESTORE),

    ("allow_remote_connections", _("Allowed remote UI connections"), "localhost",
     _("""Enter a list of trusted IPs, separated by commas. Remote
     connections from any of them will be allowed. You can trust any
     IP using a single '*' as field value. You can also trust ranges of
     IPs using the '*' character as a wildcard (for instance 192.168.0.*).
     The localhost IP will always be trusted. Type 'localhost' in the
     field to trust this only address."""),
     IP_LIST, RESTORE),

    ("display_headers", _("Headers to display in message review"), ("Subject", "From"),
     _("""When reviewing messages via the web user interface, you are
     presented with various information about the message.  By default, you
     are shown the subject and who the message is from.  You can add other
     message headers to display, however, such as the address the message
     is to, or the date that the message was sent."""),
     HEADER_NAME, RESTORE),

    ("display_received_time", _("Display date received in message review"), False,
     _("""When reviewing messages via the web user interface, you are
     presented with various information about the message.  If you set
     this option, you will be shown the date that the message was received.
     """),
     BOOLEAN, RESTORE),

    ("display_score", _("Display score in message review"), False,
     _("""When reviewing messages via the web user interface, you are
     presented with various information about the message.  If you
     set this option, this information will include the score that
     the message received when it was classified.  You might wish to
     see this purely out of curiousity, or you might wish to only
     train on messages that score towards the boundaries of the
     classification areas.  Note that in order to use this option,
     you must also enable the option to include the score in the
     message headers."""),
     BOOLEAN, RESTORE),

    ("display_adv_find", _("Display the advanced find query"), False,
     _("""Present advanced options in the 'Word Query' box on the front page,
     including wildcard and regular expression searching."""),
     BOOLEAN, RESTORE),

    ("default_ham_action", _("Default training for ham"), _("discard"),
     _("""When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as ham?"""),
     (_("ham"), _("spam"), _("discard"), _("defer")), RESTORE),

    ("default_spam_action", _("Default training for spam"), _("discard"),
     _("""When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as spam?"""),
     (_("ham"), _("spam"), _("discard"), _("defer")), RESTORE),

    ("default_unsure_action", _("Default training for unsure"), _("defer"),
     _("""When presented with the review list in the web interface,
     which button would you like checked by default when the message
     is classified as unsure?"""),
     (_("ham"), _("spam"), _("discard"), _("defer")), RESTORE),

    ("ham_discard_level", _("Ham Discard Level"), 0.0,
     _("""Hams scoring less than this percentage will default to being
     discarded in the training interface (they won't be trained). You'll
     need to turn off the 'Train when filtering' option, above, for this
     to have any effect"""),
     REAL, RESTORE),

    ("spam_discard_level", _("Spam Discard Level"), 100.0,
     _("""Spams scoring more than this percentage will default to being
     discarded in the training interface (they won't be trained). You'll
     need to turn off the 'Train when filtering' option, above, for this
     to have any effect"""),
     REAL, RESTORE),

    ("http_authentication", _("HTTP Authentication"), "None",
     _("""This option lets you choose the security level of the web interface.
     When selecting Basic or Digest, the user will be prompted a login and a
     password to access the web interface. The Basic option is faster, but
     transmits the password in clear on the network. The Digest option
     encrypts the password before transmission."""),
     ("None", "Basic", "Digest"), RESTORE),

    ("http_user_name", _("User name"), "admin",
     _("""If you activated the HTTP authentication option, you can modify the
     authorized user name here."""),
     r"[\w]+", RESTORE),

    ("http_password", _("Password"), "admin",
     _("""If you activated the HTTP authentication option, you can modify the
     authorized user password here."""),
     r"[\w]+", RESTORE),

    ("rows_per_section", _("Rows per section"), 10000,
     _("""Number of rows to display per ham/spam/unsure section."""),
     INTEGER, RESTORE),
  ),

  "imap" : (
    ("server", _("Server"), (),
     _("""These are the names and ports of the imap servers that store your
     mail, and which the imap filter will connect to - for example:
     mail.example.com or imap.example.com:143.  The default IMAP port is
     143 (or 993 if using SSL); if you connect via one of those ports, you
     can leave this blank. If you use more than one server, use a comma
     delimited list of the server:port values."""),
     SERVER, DO_NOT_RESTORE),

    ("username", _("Username"), (),
     _("""This is the id that you use to log into your imap server.  If your
     address is funkyguy@example.com, then your username is probably
     funkyguy."""),
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("password", _("Password"), (),
     _("""That is that password that you use to log into your imap server.
     This will be stored in plain text in your configuration file, and if
     you have set the web user interface to allow remote connections, then
     it will be available for the whole world to see in plain text.  If
     I've just freaked you out, don't panic <wink>.  You can leave this
     blank and use the -p command line option to imapfilter.py and you will
     be prompted for your password."""),
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("expunge", _("Purge//Expunge"), False,
     _("""Permanently remove *all* messages flagged with //Deleted on logout.
     If you do not know what this means, then please leave this as
     False."""),
     BOOLEAN, RESTORE),

    ("use_ssl", _("Connect via a secure socket layer"), False,
     _("""Use SSL to connect to the server. This allows spambayes to connect
     without sending the password in plain text.

     Note that this does not check the server certificate at this point in
     time."""),
     BOOLEAN, DO_NOT_RESTORE),

    ("filter_folders", _("Folders to filter"), ("INBOX",),
     _("""Comma delimited list of folders to be filtered"""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("unsure_folder", _("Folder for unsure messages"), "",
     _(""""""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("spam_folder", _("Folder for suspected spam"), "",
     _(""""""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("ham_folder", _("Folder for ham messages"), "",
     _("""If you leave this option blank, messages classified as ham will not
     be moved.  However, if you wish to have ham messages moved, you can
     select a folder here."""),
     IMAP_FOLDER, DO_NOT_RESTORE),
    
    ("ham_train_folders", _("Folders with mail to be trained as ham"), (),
     _("""Comma delimited list of folders that will be examined for messages
     to train as ham."""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("spam_train_folders", _("Folders with mail to be trained as spam"), (),
     _("""Comma delimited list of folders that will be examined for messages
     to train as spam."""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("move_trained_spam_to_folder", _("Folder to move trained spam to"), "",
     _("""When training, all messages in the spam training folder(s) (above)
     are examined - if they are new, they are used to train, if not, they
     are ignored.  This examination does take time, however, so if speed
     is an issue for you, you may wish to move messages out of this folder
     once they have been trained (either to delete them or to a storage
     folder).  If a folder name is specified here, this will happen
     automatically.  Note that the filter is not yet clever enough to
     move the mail to different folders depending on which folder it
     was originally in - *all* messages will be moved to the same
     folder."""),
     IMAP_FOLDER, DO_NOT_RESTORE),

    ("move_trained_ham_to_folder", _("Folder to move trained ham to"), "",
     _("""When training, all messages in the ham training folder(s) (above)
     are examined - if they are new, they are used to train, if not, they
     are ignored.  This examination does take time, however, so if speed
     is an issue for you, you may wish to move messages out of this folder
     once they have been trained (either to delete them or to a storage
     folder).  If a folder name is specified here, this will happen
     automatically.  Note that the filter is not yet clever enough to
     move the mail to different folders depending on which folder it
     was originally in - *all* messages will be moved to the same
     folder."""),
     IMAP_FOLDER, DO_NOT_RESTORE),
  ),

  "ZODB" : (
    ("zeo_addr", _(""), "",
     _(""""""),
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("event_log_file", _(""), "",
     _(""""""),
     IMAP_ASTRING, RESTORE),

    ("folder_dir", _(""), "",
     _(""""""),
     PATH, DO_NOT_RESTORE),

    ("ham_folders", _(""), "",
     _(""""""),
     PATH, DO_NOT_RESTORE),

    ("spam_folders", _(""), "",
     _(""""""),
     PATH, DO_NOT_RESTORE),

    ("event_log_severity", _(""), 0,
     _(""""""),
     INTEGER, RESTORE),

    ("cache_size", _(""), 2000,
     _(""""""),
     INTEGER, RESTORE),
  ),

  "imapserver" : (
    ("username", _("Username"), "",
     _("""The username to use when logging into the SpamBayes IMAP server."""),
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("password", _("Password"), "",
     _("""The password to use when logging into the SpamBayes IMAP server."""),
     IMAP_ASTRING, DO_NOT_RESTORE),

    ("port", _("IMAP Listen Port"), 143,
     _("""The port to serve the SpamBayes IMAP server on."""),
     PORT, RESTORE),
  ),

  "globals" : (
    ("verbose", _("Verbose"), False,
     _(""""""),
     BOOLEAN, RESTORE),

    ("dbm_type", _("Database storage type"), "best",
     _("""What DBM storage type should we use?  Must be best, db3hash,
     dbhash or gdbm.  Windows folk should steer clear of dbhash.  Default
     is "best", which will pick the best DBM type available on your
     platform."""),
     ("best", "db3hash", "dbhash", "gdbm"), RESTORE),

    ("proxy_username", _("HTTP Proxy Username"), "",
     _("""The username to give to the HTTP proxy when required.  If a
     username is not necessary, simply leave blank."""),
     r"[\w]+", DO_NOT_RESTORE),
    ("proxy_password", _("HTTP Proxy Password"), "",
     _("""The password to give to the HTTP proxy when required.  This is
     stored in clear text in your configuration file, so if that bothers
     you then don't do this.  You'll need to use a proxy that doesn't need
     authentication, or do without any SpamBayes HTTP activity."""),
     r"[\w]+", DO_NOT_RESTORE),
    ("proxy_server", _("HTTP Proxy Server"), "",
     _("""If a spambayes application needs to use HTTP, it will try to do so
     through this proxy server.  The port defaults to 8080, or can be
     entered with the server:port form."""),
     SERVER, DO_NOT_RESTORE),

    ("language", _("User Interface Language"), ("en_US",),
     _("""If possible, the user interface should use a language from this
     list (in order of preference)."""),
     r"\w\w(?:_\w\w)?", RESTORE),
  ),
  "Plugin": (
    ("xmlrpc_path", _("XML-RPC path"), "/sbrpc",
     _("""The path to respond to."""),
     r"[\w]+", RESTORE),
    ("xmlrpc_host", _("XML-RPC host"), "localhost",
     _("""The host to listen on."""),
     SERVER, RESTORE),
    ("xmlrpc_port", _("XML-RPC port"), 8001,
     _("""The port to listen on."""),
     r"[\d]+", RESTORE),
    ),
}

# `optionsPathname` is the pathname of the last ini file in the list.
# This is where the web-based configuration page will write its changes.
# If no ini files are found, it defaults to bayescustomize.ini in the
# current working directory.
optionsPathname = None

# The global options object - created by load_options
options = None

def load_options():
    global optionsPathname, options
    options = OptionsClass()
    options.load_defaults(defaults)

    # Maybe we are reloading.
    if optionsPathname:
        options.merge_file(optionsPathname)

    alternate = None
    if hasattr(os, 'getenv'):
        alternate = os.getenv('BAYESCUSTOMIZE')
    if alternate:
        filenames = alternate.split(os.pathsep)
        options.merge_files(filenames)
        optionsPathname = os.path.abspath(filenames[-1])
    else:
        alts = []
        for path in ['bayescustomize.ini', '~/.spambayesrc']:
            epath = os.path.expanduser(path)
            if os.path.exists(epath):
                alts.append(epath)
        if alts:
            options.merge_files(alts)
            optionsPathname = os.path.abspath(alts[-1])

    if not optionsPathname:
        optionsPathname = os.path.abspath('bayescustomize.ini')
        if sys.platform.startswith("win") and \
           not os.path.isfile(optionsPathname):
            # If we are on Windows and still don't have an INI, default to the
            # 'per-user' directory.
            try:
                from win32com.shell import shell, shellcon
            except ImportError:
                # We are on Windows, with no BAYESCUSTOMIZE set, no ini file
                # in the current directory, and no win32 extensions installed
                # to locate the "user" directory - seeing things are so lamely
                # setup, it is worth printing a warning
                print("NOTE: We can not locate an INI file " \
                      "for SpamBayes, and the Python for Windows extensions " \
                      "are not installed, meaning we can't locate your " \
                      "'user' directory.  An empty configuration file at " \
                      "'%s' will be used." % optionsPathname.encode('mbcs'),
                      file=sys.stderr)
            else:
                windowsUserDirectory = os.path.join(
                        shell.SHGetFolderPath(0,shellcon.CSIDL_APPDATA,0,0),
                        "SpamBayes", "Proxy")
                try:
                    if not os.path.isdir(windowsUserDirectory):
                        os.makedirs(windowsUserDirectory)
                except os.error:
                    # unable to make the directory - stick to default.
                    pass
                else:
                    optionsPathname = os.path.join(windowsUserDirectory,
                                                   'bayescustomize.ini')
                    # Not everyone is unicode aware - keep it a string.
                    optionsPathname = optionsPathname.encode("mbcs")
                    # If the file exists, then load it.
                    if os.path.exists(optionsPathname):
                        options.merge_file(optionsPathname)


def get_pathname_option(section, option):
    """Return the option relative to the path specified in the
    gloabl optionsPathname, unless it is already an absolute path."""
    filename = os.path.expanduser(options.get(section, option))
    if os.path.isabs(filename):
        return filename
    return os.path.join(os.path.dirname(optionsPathname), filename)

# Ideally, we should not create the objects at import time - but we have
# done it this way forever!
# We avoid having the options loading code at the module level, as then
# the only way to re-read is to reload this module, and as at 2.3, that
# doesn't work in a .zip file.
load_options()
