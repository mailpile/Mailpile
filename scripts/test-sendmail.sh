#!/bin/bash
OUTPUT="$(dirname $0)/../testing/tmp/sent.mbx"
mkdir -p "$(dirname $OUTPUT)"
touch "$OUTPUT"
if [ -f "$OUTPUT" ]; then
  echo "From fake@localhost $(date)" >> "$OUTPUT"
  echo "X-Args: $@" >> "$OUTPUT"
  cat >>"$OUTPUT"
  echo >>"$OUTPUT"
else
  echo "UGH: $OUTPUT"
  exit 1
fi
