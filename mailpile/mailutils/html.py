# vim: set fileencoding=utf-8 :
#
import lxml.html
import lxml.html.clean
import re


RE_HTML_BORING = re.compile(
    '(\s+|(<style[^>]*>\s*)+.*?</style>)',
    flags=re.DOTALL|re.IGNORECASE)

RE_EXCESS_WHITESPACE = re.compile(
    '\n\s*\n\s*',
    flags=re.DOTALL)

RE_HTML_NEWLINES = re.compile(
    '(<br|</(tr|table))',
    flags=re.IGNORECASE)

RE_HTML_PARAGRAPHS = re.compile(
    '(</?p|</?(title|div|html|body))',
    flags=re.IGNORECASE)

RE_HTML_LINKS = re.compile(
    '<a\s+[^>]*href=[\'"]?([^\'">]+)[^>]*>([^<]*)</a>',
    flags=re.DOTALL|re.IGNORECASE)

RE_HTML_IMGS = re.compile(
    '<img\s+[^>]*src=[\'"]?([^\'">]+)[^>]*>',
    flags=re.DOTALL|re.IGNORECASE)

RE_HTML_IMG_ALT = re.compile(
    '<img\s+[^>]*alt=[\'"]?([^\'">]+)[^>]*>',
    flags=re.DOTALL|re.IGNORECASE)

RE_XML_ENCODING = re.compile(
    '(<\?xml version=[^ ?>]*((?! +encoding=) [^ ?>]*)*)( +encoding=[^ ?>]*)',
    flags=re.DOTALL|re.IGNORECASE)


# FIXME: Decide if this is strict enough or too strict...?
SHARED_HTML_CLEANER = lxml.html.clean.Cleaner(
    page_structure=True,
    meta=True,
    links=True,
    javascript=True,
    scripts=True,
    frames=True,
    embedded=True,
    safe_attrs_only=True)


def clean_html(html):
    # Find and delete possibly conflicting xml encoding
    # declaration to prevent lxml ValueError.
    # e.g. <?xml version="1.0" encoding="ISO-8859-1"?>
    html = re.sub(RE_XML_ENCODING, r'\1', html).strip()
    return (SHARED_HTML_CLEANER.clean_html(html) if html else '')


def extract_text_from_html(html, url_callback=None):
    try:
        # We compensate for some of the limitations of lxml...
        links, imgs = [], []
        def delink(m):
            url, txt = m.group(1), m.group(2).strip()
            if url_callback is not None:
                url_callback(url, txt)
            if txt[:4] in ('http', 'www.'):
                return txt
            elif url.startswith('mailto:'):
                if '@' in txt:
                    return txt
                else:
                    return '%s (%s)' % (txt, url.split(':', 1)[1])
            else:
                links.append(' [%d] %s%s' % (len(links) + 1,
                                             txt and (txt + ': ') or '',
                                             url))
                return '%s[%d]' % (txt, len(links))

        def deimg(m):
            tag, url = m.group(0), m.group(1)
            if ' alt=' in tag:
                return re.sub(RE_HTML_IMG_ALT, '\1', tag).strip()
            else:
                imgs.append(' [%d] %s' % (len(imgs)+1, url))
                return '[Image %d]' % len(imgs)

        html = (
            re.sub(RE_XML_ENCODING, r'\1',
                re.sub(RE_HTML_PARAGRAPHS, '\n\n\\1',
                    re.sub(RE_HTML_NEWLINES, '\n\\1',
                        re.sub(RE_HTML_BORING, ' ',
                            re.sub(RE_HTML_LINKS, delink,
                                re.sub(RE_HTML_IMGS, deimg, html
            ))))))).strip()

        if html:
            try:
                html_text = lxml.html.fromstring(html).text_content()
            except XMLSyntaxError:
                html_text = _('(Invalid HTML suppressed)')
        else:
            html_text = ''

        text = (html_text +
                (links and '\n\nLinks:\n' or '') + '\n'.join(links) +
                (imgs and '\n\nImages:\n' or '') + '\n'.join(imgs))

        return re.sub(RE_EXCESS_WHITESPACE, '\n\n', text).strip()
    except:
        import traceback
        traceback.print_exc()
        return html


if __name__ == "__main__":
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
