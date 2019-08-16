#!/bin/bash
echo $(git status --porcelain -b |head -1 |cut -f1 -d.)@$(git rev-parse HEAD|cut -b1-12) |cut -f 2 -d" "
