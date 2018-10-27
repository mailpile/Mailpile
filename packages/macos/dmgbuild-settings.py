import biplist
import json
import os

# Load our settings from the appdmg json config
with open(os.getenv('APPDMG_CONFIG'), 'r') as fd:
    _json_data = json.load(fd)


# A helpful helper (copied from dmgbuild settings.py example)
def icon_from_app(app_path):
    plist_path = os.path.join(app_path, 'Contents', 'Info.plist')
    plist = biplist.readPlist(plist_path)
    icon_name = plist['CFBundleIconFile']
    icon_root, icon_ext = os.path.splitext(icon_name)
    if not icon_ext:
        icon_ext = '.icns'
    icon_name = icon_root + icon_ext
    return os.path.join(app_path, 'Contents', 'Resources', icon_name)


# Basics
appname      = _json_data.get('title', 'Mailpile')
volume_name  = _json_data.get('title', 'Mailpile')
format       = _json_data.get('format', 'ULFO')
background   = _json_data.get('background', '#fff')
default_view = 'icon-view'
icon_size    = float(_json_data.get('icon-size', '64pt').replace('pt', ''))
window_rect  = ((
        _json_data.get('window', {}).get('position', {}).get('x', 100),
        _json_data.get('window', {}).get('position', {}).get('y', 100)
    ), (
        _json_data.get('window', {}).get('size', {}).get('width', 400),
        _json_data.get('window', {}).get('size', {}).get('height', 400)))

# Files to include, derived badge icon, etc.
files = []
symlinks = {}
icon_locations = {}
for _elem in _json_data.get('contents', []):
    _name = os.path.basename(_elem['path'])
    if _elem.get('type') == 'link':
        symlinks[_name] = _elem['path']
    else:
        files.append(_elem['path'])
        # Will be used to badge the system's Removable Disk icon
        if _elem['path'].endswith('.app'):
            badge_icon = icon_from_app(_elem['path'])

    icon_locations[_name] = (_elem['x'], _elem['y'])

# EOF #
