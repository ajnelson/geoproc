#!/usr/bin/env python3

__version__ = "0.1.0"

import argparse
import os
import sys

from reconstruct import ForensicPath

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

def main():
    global args
    if args.output:
        outfile_name = args.output
    else:
        outfile_name = "sorted_" + os.path.basename(args.feature_file)
    with open(args.feature_file, "rb") as feature_file:
        with open(outfile_name, "wb") as outfile:
            lines = []
            for line in feature_file:
                if line.startswith(b"#"):
                    continue
                fp = ForensicPath(line.split(b"\t")[0])
                lines.append( (fp, line) )
            dprint("lines length: %d" % len(lines))
            lines.sort()
            for line in lines:
                outfile.write(line[1])
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sort a single Bulk Extractor feature file.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug printing (writes to stderr).")
    parser.add_argument("-o", "--output", help="Name of output file.  Defaults to input file's basename prefixed with 'sorted_'.")
    parser.add_argument("feature_file", help="Bulk Extractor feature file.")
    args = parser.parse_args()
    main()
