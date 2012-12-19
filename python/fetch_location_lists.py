#!/usr/bin/env python3

__version__ = "0.1.1"

import geoproc_cfg

def main():
    lookupconn = None
    lookupcur = None
    import mysql.connector as mdb
    lookupconn = mdb.connect(
      host=geoproc_cfg.config.get("mysql", "maxmind_server"),
      user=geoproc_cfg.config.get("mysql", "maxmind_read_username"),
      password=geoproc_cfg.db_password("maxmind_read_password_file"),
      db=geoproc_cfg.config.get("mysql", "maxmind_schema"),
      use_unicode=True
    )
    lookupcur = lookupconn.cursor(cursor_class=geoproc_cfg.MySQLCursorDict)
    
    for locfield in ["country","region","city"]:
        with open("distinct_%s.txt" % locfield, "w") as outfile:
            lookupcur.execute("""
              SELECT
                %(locfield)s
              FROM
                Distinct_%(locfield)s
              ;
            """ % {"locfield":locfield})
            for row in lookupcur:
                outfile.write(row[locfield] + "\n")

if __name__ == "__main__":
    main()
