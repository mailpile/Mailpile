#!/bin/bash
(
    cat <<tac
{
    "app_name": "Indicator Test",
    "indicator_icon": "$(pwd)/mailpile.png",
    "indicator_menu": [
        {
            "label": "Indicator test",
            "item": "info"
        },{
            "label": "XKCD",
            "item": "xkcd",
            "op": "show",
            "args": ["https://xkcd.com/"],
            "sensitive": false
        }
    ]
}
OK GO
tac

sleep 10
echo 'set_menu_sensitive {"item": "xkcd"}'

sleep 60

) | python gui-o-matic.py
