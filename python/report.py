#!/usr/bin/env python3
"""
report.py - create report on geoproc results
"""

__version__ = "0.0.3"

import os
import argparse
import re
import datetime
import sqlite3

import success

REPORT_HEAD = """<!doctype html>
<html>
  <head>
    <title>Geoproc report on image %(image_name)s</title>
  </head>
  <body>
    <h1>Geoproc report on image <acronym title="%(image_path)s">%(image_name)s</acronym></h1>"""

REPORT_FOOT = """  </body>
</html>"""

def image_name_from_output_directory(outdir):
    return os.path.basename(outdir)

def do_belief_report():
    global args

    precisionconn = None
    precisioncur = None
    if args.precision_db:
        precisionconn = sqlite3.connect(args.precision_db)
        #Don't lock db
        precisionconn.row_factory = sqlite3.Row
        precisioncur = precisionconn.cursor()

    #Start assembling locations
    if success.success(os.path.join(args.output_directory, "analyze_cookie_files.sh.status.log")):
        inconn = sqlite3.connect(os.path.join(args.output_directory, "analyze_cookie_files.sh", "cookie_files_votes.db"))
        #Don't lock db
        inconn.row_factory = sqlite3.Row
        incur = inconn.cursor()
        for row in incur.execute("SELECT * FROM cookie_files_votes;"):
            break #TODO
        inconn.close()

    print("""    <h2><a name="location_beliefs">Location beliefs</a></h2>
    <p>This location has artifacts that indicate it was in the following locations:</p>
    <table>
      <thead>
        <tr>
          <th>Location name</th>
          <th>Latitude</th>
          <th>Longitude</th>
          <th>Shurity</th>
        </tr>
      </thead>
      <tfoot></tfoot>
      <tbody>""")

    for x in [{
      "location":"(Ranked implementation pending)",
      "latitude":1.1,
      "longitude":2.2,
      "shurity":1.0
    }]:
        print("    <tr><td>%(location)s</td><td>%(latitude)f</td><td>%(longitude)f</td><td>%(shurity)f</td></tr>" % x)

    print("""      </tbody>
    </table>""")

def exit_status_from_script_directory(outdir):
    with open(outdir + ".status.log", "r") as statuslog:
        status = statuslog.read(8).strip()
        if status.isdigit():
            return int(status)
        elif status == "imported":
            return "(Imported)"
        elif status == "skipped":
            return "(Skipped)"
    return None

def make_process_status_list(outdir):
    """
    This subroutine builds a list of the geoproc scripts invoked, checking their status and recording their paths.
    The list is of dictionaries, keys noted in the function body.
    """
    retval = []
    for (dirpath, dirnames, filenames) in os.walk(outdir):
        for scriptdir in dirnames:
            if not scriptdir.endswith(".sh"):
                continue
            newdict = {}
            sop = os.path.join(dirpath,scriptdir)
            newdict["script_output_path"] = sop
            newdict["script_name"] = scriptdir
            newdict["exit_status"] = str(exit_status_from_script_directory(sop))
            retval.append(newdict)
        break
    return retval

#TODO Need a better term for the shell scripts invoked by Make...component? process?
def do_process_status_report():
    global args
    print("""    <h2><a name="status_report">Processing status report</a></h2>
    <p>The following table lists the exit status of each component of the report dependency graph.  A successful process exits with status 0.  If there are any errors, you should investigate that component's logs.</p>
    <table>
      <thead><tr><th>Component</th><th>Exit status</th></tr></thead>
      <tfoot></tfoot>
      <tbody>""")

    for procstat in sorted(make_process_status_list(args.output_directory), key=lambda x:x["script_name"]):
        print("        <tr><td>%(script_name)s</td><td>%(exit_status)s</td></tr>" % procstat)

    print("""      </tbody>
    </table>""")

def do_timestamp():
    print("""    <hr />
    <p>Report generated at %(timestamp)s.</p>""" % {"timestamp":datetime.datetime.now()})

def do_toc():
    print("""    <h2>Contents</h2>
    <ul>
      <li><a href="#location_beliefs">Location beliefs</a></li>
      <li><a href="#status_report">Processing status report</a></li>
    </ul>""")

def main():
    global args
    if not os.path.isdir(args.output_directory):
        raise Exception("Given output directory is not a directory.")
    print(REPORT_HEAD % {
      "image_name":os.path.basename(args.output_directory),
      "image_path":args.output_directory #TODO Use image path vs. output path
    })
    do_toc()
    do_belief_report()
    do_process_status_report()
    do_timestamp()
    print(REPORT_FOOT)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Produce report document summarizing image location beliefs and processing status.")
    parser.add_argument("-p", "--precision_db", help="SQLite database containing evaluated precision of features.")
    parser.add_argument("output_directory", help="Output directory of the geoproc processing.")
    args = parser.parse_args()
    main()
