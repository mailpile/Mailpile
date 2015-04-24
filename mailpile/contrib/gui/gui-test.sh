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
echo 'show_splash_screen {"image": "icons-light/normal.png", "message": "Hello world!", "progress_bar": true}'

sleep 2
echo 'update_splash_screen {"progress": 0.2}'
echo 'set_status_normal {}'

sleep 2
echo 'update_splash_screen {"progress": 0.5, "message": "Woohooooo"}'
echo 'update_splash_screen {"progress": 0.5}'
echo 'set_menu_sensitive {"item": "xkcd"}'
echo 'notify_user {"message": "This is a notification"}'

sleep 2
echo 'update_splash_screen {"progress": 1.0}'
echo 'set_status_working {}'
sleep 2
echo 'hide_splash_screen {}'
echo 'set_status_attention {}'

sleep 2
echo 'set_menu_label {"item": "xkcd", "label": "No really, XKCD"}'

sleep 30
echo 'set_status_shutdown {}'

sleep 5

) | python gui-o-matic.py
