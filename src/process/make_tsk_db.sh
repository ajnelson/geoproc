#!/bin/bash
if [ $# -lt 2 ]; then
  echo "Usage: $0 <image> <out_directory>"
  exit 1
fi

tsk_loaddb -d"$2/tskout.db" "$1"
