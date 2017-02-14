import copy
import re

from mailpile.util import *


##[ Keyword experiments ]#####################################################

RE_QUOTES = re.compile(r'^(>\s*)+')
RE_CLEANPARA = re.compile(r'[>"\*\'\s]')

def paragraph_id_extractor(index, msg, ctype, textpart, **kwargs):
    """Create search index terms to identify paragraphs."""
    kws = set([])
    try:
        if not ctype == 'text/plain':
            return kws
        if not index.config.prefs.get('experiment_para_kws'):
            return kws

        para = {'text': '', 'qlevel': 0}
        def end_para():
            txt = para.get('text', '')
            if (len(txt) > 60 and
                    not ('unsubscribe' in txt and 'http' in txt) and
                    not ('@lists' in txt or '/mailman/' in txt) and
                    not (txt.endswith(':'))):
                txt = re.sub(RE_CLEANPARA, '', txt)[-120:]
#               print 'PARA: %s' % txt
                kws.add('%s:p' % md5_hex(txt))
            para.update({'text': '', 'qlevel': 0})

        for line in textpart.splitlines():
            if line in ('-- ', '- -- ', '- --'):
                return kws

            # Find the quote markers...
            markers = re.match(RE_QUOTES, line)
            ql = len((markers.group(0) if markers else '').strip())

            # Paragraphs end when...
            if ((ql == 0 and line.endswith(':')) or  # new quote starts
                    (ql != para['qlevel']) or        # quote level changes
                    (ql == len(line)) or             # blank lines
                    (line[:2] == '--')):             # on -- dividers
                end_para()

            para['qlevel'] = ql
            if not line[:2] in ('--', ):
                para['text'] += line
        end_para()
    except: # AttributeError:
        import traceback
        traceback.print_exc()
        pass
    return kws
