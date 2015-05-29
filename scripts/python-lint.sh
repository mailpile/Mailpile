#!/bin/bash
command -v pep8 >/dev/null 2>&1 || {
    echo >&2 "pep8 not found.";
    exit 1;
}
pep8 --ignore W191 ./mailpile
if [ $? -eq 0 ]; then
   echo "pep8 returned with success"
   exit 0
else
   echo "pep8 returned with failure"
   exit 1
fi
