# This plugin associate one (or more) tags to mailboxes

import mailpile.plugins


##[ Configuration ]###########################################################

mailpile.plugins.register_config_section(
    'prefs', 'mbtag', ["Auto-tagging based on incoming mailbox", str, []])


##[ Keywords ]################################################################

def filter_hook(session, msg_mid, msg, keywords):
    mailbox = [int(k.rsplit(":",1)[0], 36) for k in keywords if k.endswith(":mailbox")]
    if mailbox:
        for mb_index, mb_tags in enumerate(session.config.prefs.mbtag):
            if mb_index in mailbox:
                for tag in mb_tags.split(","):
                    tag = session.config.get_tag(tag.strip())
                    if tag:
                        keywords.add("%s:in" % tag._key)
    #print(keywords)
    return keywords


mailpile.plugins.register_filter_hook_post('00-mbtag', filter_hook)
