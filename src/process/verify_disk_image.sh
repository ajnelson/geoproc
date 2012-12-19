#!/bin/bash
if [ $# -lt 2 ]; then
  echo "Usage: $0 <image> <out_directory>"
  exit 1
fi

#Substring test c/o Stack Overflow: http://stackoverflow.com/a/407229/1207160
ext=${1: -4}
rc=0
if [ "$ext" == ".aff" ] || [ "$ext" == ".AFF" ]; then
  echo "Debug: Verifying AFF file..." >&2
  affverify "$1"
  rc=$?
elif [ "$ext" == ".E01" ] || [ "$ext" == ".e01" ]; then
  echo "Debug: Verifying E01 file..." >&2
  ewfverify "$1"
  rc=$?
else
  echo "Warning: this program doesn't know how to verify the image type requested." >&2
fi

exit $rc
