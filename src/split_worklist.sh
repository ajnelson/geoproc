#!/bin/bash
if [ $# -lt 2 ]; then
  echo "Usage: $0 <split number> <worklist file>" >&2
  echo "Randomly splits lines of worklist file into split-number files.  Results start with 'sorted-'." >&2
  echo "This script assumes the worklist file doesn't have spaces in its name."
  exit 1
fi

#Exit on error
set -e

SORT=$(which gsort)
if [ -z "$SORT" ]; then
  SORT=$(which sort)
fi

SPLIT=$(which gsplit)
if [ -z "$SPLIT" ]; then
  SPLIT=$(which split)
fi

factor=$1
worklist=$2

$SORT --random-sort "$worklist" >"${worklist}_random.txt"
$SPLIT --number=l/$factor "${worklist}_random.txt" "split${factor}_${worklist}_"
for x in $(ls "split${factor}_${worklist}_"*); do
  $SORT "$x" >"sorted_$x"
  rm "$x"
done
rm "${worklist}_random.txt"
