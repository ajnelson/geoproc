#!/usr/bin/python3

__version__ = "0.1.2"

import os
import argparse
import sqlite3
import collections
import mysql.connector

import dfxml
import geoproc_cfg
import geoproc_library

SQL_CREATE_IPV4S_VOTES = """
CREATE TABLE ipv4s_votes (
  forensic_path TEXT,
  fiwalk_id NUMBER,
  fs_obj_id NUMBER,
  obj_id NUMBER,
  ipv4 TEXT,
  network_proxy_software_detected BOOLEAN,
  believed_timestamp TEXT,
  selected_time_type TEXT,
  maxmind_ipv4_time TEXT,
  country TEXT,
  region TEXT,
  city TEXT,
  postalCode TEXT,
  latitude NUMBER,
  longitude NUMBER,
  database_queried BOOLEAN,
  is_socket_address BOOLEAN,
  cksum_ok BOOLEAN,
  src_or_dst TEXT,
  pair_found BOOLEAN,
  ipv4_notes TEXT
);
"""

def main():
    global args
    #Connect to anno db if available
    annoconn, annocur = geoproc_library.connect_to_fs_anno_db(args.anno)

    #Connect to db
    cfg = geoproc_cfg.config
    refconn = mysql.connector.Connect(
      host=cfg.get("mysql", "maxmind_server"),
      user=cfg.get("mysql", "maxmind_read_username"),
      password=geoproc_cfg.db_password("maxmind_read_password_file"),
      db=cfg.get("mysql", "maxmind_schema"),
      use_unicode=True
    )
    if refconn is None:
        raise Exception("Error: Could not define lookup cursor.")
    refcur = refconn.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)

    outconn = sqlite3.connect("ipv4s_votes.db")
    outconn.isolation_level = "EXCLUSIVE"
    outconn.row_factory = sqlite3.Row
    outcur = outconn.cursor()

    outcur.execute(SQL_CREATE_IPV4S_VOTES)

    pairing_dict = collections.defaultdict(list)
    ip_set = set([])
    for (ipno, (forensic_path, ipv4, ipv4_notes)) in enumerate(geoproc_library.bulk_extractor_ips(args.be_dir)):
        pairing_dict[forensic_path].append((ipv4, ipv4_notes))
        ip_set.add(ipv4)

    #Unfortunately, there isn't much to do for timestamps without file system or network time information. #TODO Add time interface
    dummy_dftime = dfxml.dftime("2009-05-01T00:00:00Z")

    ips_to_locs = geoproc_library.ips_to_locations(refcur, None, ip_set)

    for forensic_path in pairing_dict:
        #Determine if we have a pair
        entries_at_path = pairing_dict[forensic_path]
        pair_found = len(entries_at_path) == 2
        for (ipv4, ipv4_notes) in entries_at_path:
            outdict = dict()
            outdict["believed_timestamp"] = dummy_dftime.iso8601()
            outdict["forensic_path"] = forensic_path
            outdict["ipv4"] = ipv4
            outdict["ipv4_notes"] = ipv4_notes
            if "cksum-bad" in ipv4_notes:
                outdict["cksum_ok"] = False
            elif "cksum-ok" in ipv4_notes:
                outdict["cksum_ok"] = True
            #None, otherwise
            outdict["is_socket_address"] = "sockaddr" in ipv4_notes
            outdict["pair_found"] = pair_found
            if "(src)" in ipv4_notes:
                outdict["src_or_dst"] = "src"
            elif "dst" in ipv4_notes:
                outdict["src_or_dst"] = "dst"
            #None, otherwise 
            annorecs = geoproc_library.forensic_path_to_anno_recs(annocur, outdict["forensic_path"])
            if annorecs and len(annorecs) > 1:
                sys.stderr.write("Warning: Multiple files found to own forensic path %r. Only using first.  This may cause strange results.\n" % outdict["forensic_path"])
            if annorecs and len(annorecs) > 0:
                annorec = annorecs[0]
                outdict["obj_id"] = annorec.get("obj_id")
                outdict["fs_obj_id"] = annorec.get("fs_obj_id")
                outdict["fiwalk_id"] = annorec.get("fiwalk_id")

            if ipv4 in ips_to_locs:
                for key in [
                  "maxmind_ipv4_time",
                  "country",
                  "region",
                  "city",
                  "postalCode",
                  "latitude",
                  "longitude"
                ]:
                    outdict[key] = ips_to_locs[ipv4][key]

            geoproc_library.insert_db(outcur, "ipv4s_votes", outdict)
    outconn.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Map ipv4 addresses found by Bulk Extractor")
    parser.add_argument("be_dir", help="Bulk Extractor output directory.")
    parser.add_argument("-a", "--anno", help="Annotation database of Fiwalk and TSK-db")
    args = parser.parse_args()

    if not os.path.isdir(args.be_dir):
        raise ValueError("be_dir must be a directory.")

    main()
