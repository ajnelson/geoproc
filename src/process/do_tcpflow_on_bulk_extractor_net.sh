#!/bin/bash

#TODO Check for tcpflow and have ./configure set this script to fail out without it
#exit 38 #38 == ENOSYS, function not implemented

outdir="$2"

bulk_extractor_output="${outdir/%do_tcpflow_on_bulk_extractor_net.sh/do_bulk_extractor.sh}/bulk_extractor.out"

pcapfile="${bulk_extractor_output}/packets.pcap"

if [ -f $pcapfile ]; then
  tcpflow -r "$pcapfile" -o "$outdir"
else
  echo "No pcap file available from bulk_extractor output directory:" >&2
  echo $bulk_extractor_output >&2
  exit 0 #2 == ENOENT, no such file or directory; but we'll just call nothing-in-nothing-out a successful invocation of this script.
fi
