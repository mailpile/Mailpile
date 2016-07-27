#! /bin/bash

SCRIPTDIR=`cd "$(dirname "$0")" && pwd`
# move into the newly created source repo
cd $SCRIPTDIR

# activate the virtual Python environment
source mp-virtualenv/bin/activate

./mp
