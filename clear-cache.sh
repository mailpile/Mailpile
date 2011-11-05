#!/bin/bash
#
# For testing, this clears the Linux VM cache so we can get real numbers
#
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null
