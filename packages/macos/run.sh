#!/bin/sh
cd "${0%/*}" # Sets current directory to the directory in which this script is located.
PATH=`pwd`/build/bin/:$PATH
export PATH
python ../../mp
