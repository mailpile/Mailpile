#!/bin/bash

TERMS="-s http
       -s bjarni
       -s ewelina
       -s att:pdf
       -s subject:bjarni
       -s cowboy
       -s unknown
       -s zyxel"

for size in 126 62 46 30; do
  ./mailpile.py -S postinglist_kb=$size -O
  sync
  for run in 1 2 3; do
    echo --- $run ---
    sudo ./clear-cache.sh
    ./mailpile.py -S num_results=50 -S default_order=rev-date $TERMS $TERMS \
      |grep Elapsed:
  done
done
