#!/bin/bash
if [ $# -lt 2 ]; then
  echo "Usage: $0 <image> <out_directory>"
  exit 1
fi

path_to_fiout="$2/fiout.xml"

fiwalk -X"$path_to_fiout" -f "$1" -G0

if [ $(grep '<volume ' "$path_to_fiout" | wc -l) -eq 0 ]; then
  echo "Warning: Fiwalk could not extract any partitions from the disk image." >&2
  #If this is a problem, exit 42 (errno of "No message of desired type").
fi
