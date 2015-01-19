#!/bin/bash
OUTPUT="$(dirname $0)/../mailpile/tests/data/tmp/sent.mbx"
mkdir -p "$(dirname $OUTPUT)"
touch "$OUTPUT"
if [ -f "$OUTPUT" ]; then
  echo "From fake@localhost $(date)" >> "$OUTPUT"
  echo "X-Args: $@" >> "$OUTPUT"
  cat >>"$OUTPUT"
  echo >>"$OUTPUT"
  sync
else
  echo "UGH: $OUTPUT"
  exit 1
fi
