#!/usr/bin/env python3

__version__ = "0.3.0"

import os
import sys
import sqlite3

import argparse

import geoproc_library

SQL_CREATE_LOCATION_GROUND_TRUTH = """
CREATE TABLE location_ground_truth (
  image_id TEXT NOT NULL,
  country TEXT,
  region TEXT,
  city TEXT,
  postalCode TEXT
);
"""

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

#TODO Data note: The Norby phone might have just been used in Pittsburgh proper

def main():
    global args

    if os.path.isfile(args.db_name):
        if args.zap:
            os.remove(args.db_name)
        else:
            raise Exception("Output database already exists; aborting.")

    conn = sqlite3.connect(args.db_name)
    conn.isolation_level = "EXCLUSIVE"
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(SQL_CREATE_LOCATION_GROUND_TRUTH)
    conn.commit()

    gtcsv = open(args.ground_truth_csv, "r")
    for (lineno, line) in enumerate(gtcsv):
        if line.startswith("#"):
            continue
        line_parts = line[:-1].split("\t")
        assert len(line_parts) <= 5
        rec = {
          "image_id": line_parts[0],
          "country": line_parts[1],
          "region": line_parts[2],
          "city": line_parts[3],
          "postalCode": line_parts[4]
        }
        for key in rec.keys():
            if rec[key] == "":
                rec[key] = None
        geoproc_library.insert_db(cur, "location_ground_truth", rec)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert ground truth CSV to SQLite database.")
    parser.add_argument("-d","--debug", action="store_true", help="Enable debug messages (writes to stderr).")
    parser.add_argument("-z", "--zap", action="store_true", help="Remove output db if it already exists.")
    parser.add_argument("ground_truth_csv", help="CSV, expected format: Tab-delimited; columns image id, country, region, city, postal code.")
    parser.add_argument("db_name", help="Name of output database file.")
    args = parser.parse_args()
    main()

