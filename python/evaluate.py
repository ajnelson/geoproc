#!/usr/bin/env python3

__version__ = "0.5.0"

import argparse
import sqlite3
import sys
import os
import copy

def dprint(s):
    global args
    if args.debug:
        sys.stderr.write(str(s))
        sys.stderr.write("\n")

def main():
    if os.path.exists(args.output_db):
        if args.zap:
            os.remove(args.output_db)
        else:
            raise Exception("Output database already exists; aborting.")

    outconn = sqlite3.connect(args.output_db)
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()
    outcur.execute("ATTACH DATABASE '%s' AS aggregates;" % args.aggregate_db)
    
    locfields = ["country", "region", "city", "location"]

    tables_and_vectors = {
      "cookie_files_votes": ["record_type"],
      "email_files_votes": ["sole_recipient_domain_is_webmail", "ipv4_be_has_cksum_or_socket"],
      "exif_headers_votes": ["file_in_web_cache"],
      "ipv4s_votes": ["cksum_ok", "pair_found", "is_socket_address", "src_or_dst"]
    }

    for table in tables_and_vectors.keys():
        features = tables_and_vectors[table]

        where_clause_parts = []
        for feature in features:
            for locfield in locfields:
                where_clause_parts.append("vectors.%(feature)s IS %(locfield)s.%(feature)s" % {"feature":feature, "locfield":locfield})
        big_where_clause = " AND ".join(where_clause_parts)
        formatdict = {
          "table": table,
          "feature_cdl": ",".join(features),
          "feature_cdl_prefix_vectors": ",".join(map(lambda x: "vectors." + x, features)),
          "big_where_clause": big_where_clause
        }

        for locfield in locfields:
            iter_formatdict = copy.deepcopy(formatdict)
            iter_formatdict["locfield"] = locfield
            sqlquery = """
              CREATE TABLE %(table)s_precision_%(locfield)s AS
                SELECT
                  count(*) AS n_total_%(locfield)s,
                   SUM(correct_%(locfield)s * 1.0 / number_possible_locations) AS n_correct_%(locfield)s,
                  (SUM(correct_%(locfield)s * 1.0 / number_possible_locations)) / count(*) AS p_correct_%(locfield)s,
                  %(feature_cdl)s
                FROM
                  aggregates.%(table)s_weighted
                WHERE
                  correct_%(locfield)s IS NOT NULL
                GROUP BY
                  %(feature_cdl)s
              ;
            """ % iter_formatdict
            dprint("Debug: sqlquery = " + sqlquery)
            outcur.execute(sqlquery)
        outcur.execute("""
          CREATE TABLE %(table)s_precision_vectors AS
            SELECT DISTINCT
              %(feature_cdl)s
            FROM
              %(table)s_weighted
          ;
        """ % formatdict)
        outcur.execute("""
          CREATE TABLE %(table)s_precision AS
            SELECT
              country.n_total_country,
              country.n_correct_country,
              country.p_correct_country,
              region.n_total_region,
              region.n_correct_region,
              region.p_correct_region,
              city.n_total_city,
              city.n_correct_city,
              city.p_correct_city,
              location.n_total_location,
              location.n_correct_location,
              location.p_correct_location,
              %(feature_cdl_prefix_vectors)s
            FROM
              %(table)s_precision_country AS country,
              %(table)s_precision_region AS region,
              %(table)s_precision_city AS city,
              %(table)s_precision_location AS location,
              %(table)s_precision_vectors AS vectors
            WHERE
              %(big_where_clause)s
          ;
        """ % formatdict)
        for locfield in locfields:
            outcur.execute("DROP TABLE %(table)s_precision_%(locfield)s;" % {"locfield":locfield, "table":table})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create distributable evaluation database of feature vectors' precision.")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug printing (writes to stderr).")
    parser.add_argument("-z", "--zap", action="store_true", help="Remove output_db if it already exists.")
    parser.add_argument("aggregate_db", help="Database, output of aggregate.py.")
    parser.add_argument("output_db", help="Database to output.")
    args = parser.parse_args()

    main()
