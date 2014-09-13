#!/bin/bash
(
    cat <<tac
{
    "app_name": "Indicator Test",
    "indicator_icons": {
        "startup": "$(pwd)/icons-%(theme)s/startup.png",
        "normal": "$(pwd)/icons-%(theme)s/normal.png",
        "working": "$(pwd)/icons-%(theme)s/working.png",
        "attention": "$(pwd)/icons-%(theme)s/attention.png",
        "shutdown": "$(pwd)/icons-%(theme)s/shutdown.png"
    },
    "indicator_menu": [
        {
            "label": "Indicator test",
            "item": "info"
        },{
            "label": "XKCD",
            "item": "xkcd",
            "op": "show_url",
            "args": ["https://xkcd.com/"],
            "sensitive": false
        }
    ]
}
OK GO
tac

sleep 2
echo 'set_status_normal {}'

sleep 2
echo 'set_menu_sensitive {"item": "xkcd"}'

sleep 2
echo 'set_status_working {}'
sleep 2
echo 'set_status_attention {}'

sleep 2
echo 'set_menu_label {"item": "xkcd", "label": "No really, XKCD"}'

sleep 30
echo 'set_status_shutdown {}'

sleep 5

) | python gui-o-matic.py
