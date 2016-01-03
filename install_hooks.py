import os
import sys

def symlink_develop(config):
    if 'develop' in sys.argv:
        share_path = os.path.join(sys.prefix, 'share')

        if not os.path.exists(share_path):
            os.makedirs(share_path)

        os.symlink(
            os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                'shared-data'
            ),
            os.path.join(sys.prefix, 'share', 'mailpile')
        )
