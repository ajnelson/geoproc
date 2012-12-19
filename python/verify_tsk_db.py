#!/usr/bin/env python3

__version__ = "0.1.1"

import sys
import argparse
import sqlite3

def main():
    global args
    conn = sqlite3.connect(args.tskdb)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM tsk_files;")
    string_type = type("")
    none_type = type(None)
    rowno = 0 #enumerate() might not be able to get rowno correctly
    try:
        for row in cur:
            assert type(row["parent_path"]) in [none_type, string_type]
            assert type(row["name"]) in [none_type, string_type]
            rowno += 1
    except:
        sys.stderr.write("Note: Reached record %d.\n" % rowno)
        if row:
            sys.stderr.write("Note: The types of parent_path and name are: %r, %r.\n" % (type(row["parent_path"]), type(row["name"])))
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test characteristics of data extracted by tsk_loaddb.")
    parser.add_argument("tskdb", help="Output file of tsk_loaddb.")
    args = parser.parse_args()
    main()
