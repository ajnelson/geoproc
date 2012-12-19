#!/usr/bin/env python3

__version__ = "0.1.0"

import os
import sys
import argparse
import datetime
import collections

import geoproc_library

HTML_DOC_HEAD = """<!doctype html>
<html>
  <head>
    <title>GeoProc corpus processing summary</title>
    <style type="text/css">
      table.statusmatrix td{text-align:right;}
      th.scriptrowheader{text-align:left; font-weight:normal;}
      th.statuscolheader{text-align:right; min-width:4em; text-decoration:underline;}
    </style>
  </head>
  <body>
    <h1>%(report_title)s</h1>
"""
HTML_DOC_FOOT = """  </body>
</html>"""
HTML_DEFAULT_TITLE = "GeoProc corpus processing summary"

def do_toc():
    print("""    <h2>Contents</h2>
    <ul>
      <li><a href="#ProcessingStatistics">Processing statistics</a>
        <ul>
          <li><a href="#ErrorScripts">Script error instances</a></li>
          <li><a href="#AbortedScripts">Aborted scripts</a></li>
          <li><a href="#RunningScripts">Scripts running</a></li>
        </ul>
      </li>
      <li><a href="#Inputs">Summarized directories</a></li>
    </ul>
""")

def do_input_listing(dirs):
    print("    <h2><a name='Inputs'>Summarized directories</a></h2>")
    if len(dirs) == 0:
        print("    <p>No inputs were provided to the report.</p>")
    else:
        print("    <p>This report summarizes the following ")
        if len(dirs)==1:
            print("directory.</p>")
        else:
             print("%d directories.</p>" % len(dirs))
        print("    <ul>")
        for d in dirs:
            print("      <li>%s</li>" % d)
        print("    </ul>")

def do_processing_stats(stats):
    print("    <h2><a name='ProcessingStatistics'>Processing statistics</a></h2>")
    print("    <p>The following table summarizes the exit status statistics of each of the component scripts.</p>")
    #Columns: Exit statuses
    status_histogram = collections.defaultdict(lambda: 0) #Quick integer histogram
    script_histogram = collections.defaultdict(lambda: 0)
    rc_matrix = collections.defaultdict(lambda: collections.defaultdict(lambda: 0))
    errored_scripts = collections.defaultdict(list)
    running_scripts = collections.defaultdict(list)
    aborted_scripts  = collections.defaultdict(list)

    #Handle semantics
    good_exits = ["imported", "0", "11"]
    killed_exits = ["143"]
    unreferenceable_exits = ["skipped", ""]
    labels = {
      "": "(In progress)",
      "imported": "Imported",
      "skipped": "Skipped",
      "0": "Successful",
      "11": "11 (try again)",
      "143": "143 (aborted)"
    }

    for rec in stats:
        status_histogram[rec["status"]] += 1
        script_histogram[rec["scriptname"]] += 1
        rc_matrix[rec["scriptname"]][rec["status"]] += 1
        if rec["status"] not in good_exits and \
           rec["status"] not in killed_exits and \
           rec["status"] not in unreferenceable_exits:
            errored_scripts[rec["scriptname"]].append(rec)
        if rec["status"] == "":
            running_scripts[rec["scriptname"]].append(rec)
        if rec["status"] in killed_exits:
           aborted_scripts[rec["scriptname"]].append(rec)

    print("""    <table class='statusmatrix'>
      <thead>
        <tr>
          <th>Script</th>""")
    sorted_statuses = sorted([s for s in status_histogram if not s.isdigit()])
    sorted_statuses += map(str, sorted([int(d) for d in status_histogram if d.isdigit()]))
    
    for status in sorted_statuses:
        print("          <th class='statuscolheader'>%s</th>" % labels.get(status, status))
    print("""        </tr>
      </thead>
      <tfoot></tfoot>
      <tbody>""")
    for script in sorted(script_histogram):
        print("""        <tr>
          <th class='scriptrowheader'>%s</th>""" % script)
        for status in sorted_statuses:
            print("          <td>%d</td>" % rc_matrix[script][status])
        print("        </tr>")
    print("""      </tbody>
    </table>""")
    print("""    <h3><a name="ErrorScripts">Script error instances</a></h3>""")
    if len(errored_scripts) == 0:
        print("   <p>No errors found.</p>")
    else:
        print("""    <p>Here are file system paths of the error logs of each of the scripts that had some instance of an error.  Because one programming error indicates a class of bug, only the first five instances of an error are listed per script.</p>""")
        for script in sorted(errored_scripts.keys()):
            print("""    <h4>%s</h4>
    <ul>""" % script)
            for (recno, rec) in enumerate(errored_scripts[script]):
                print("      <li>%s.err.log</li>" % os.path.join(rec["dir"], script))
                if not args.verbose and recno > 3:
                    print("      <li>...</li>")
                    break
            print("    </ul>")
    print("""    <h3><a name="AbortedScripts">Aborted scripts</a></h3>""")
    if len(aborted_scripts) == 0:
        print("    <p>No scripts were aborted at the time of creating this report.")
    else:
        print("    <p>Some scripts were aborted at the time of creating this report.  Here are file system paths to their output directories.</p>")
        for script in sorted(aborted_scripts.keys()):
            print("""    <h4>%s</h4>
    <ul>""" % script)
            for (recno, rec) in enumerate(aborted_scripts[script]):
                print("      <li>%s</li>" % os.path.join(rec["dir"], script))
            print("    </ul>")
    print("""    <h3><a name="RunningScripts">Scripts running</a></h3>""")
    if len(running_scripts) == 0:
        print("    <p>All scripts were complete at the time of creating this report.")
    else:
        print("""    <p>Some scripts were running at the time of creating this report.  Here are file system paths to their output directories.</p>""")
        for script in sorted(running_scripts.keys()):
            print("""    <h4>%s</h4>
    <ul>""" % script)
            for (recno, rec) in enumerate(running_scripts[script]):
                print("      <li>%s</li>" % os.path.join(rec["dir"], script))
            print("    </ul>")

def aggregate_statuses(dirs):
    retval = []
    for d in dirs:
        for filename in os.listdir(d):
            if filename.endswith(".status.log"):
                retdict = {"dir":d}
                retdict["scriptname"] = filename[:-len(".status.log")]
                with open(os.path.join(d, filename), "r") as statlog:
                    retdict["status"] = statlog.readline().strip()
                if retdict.get("status") is None:
                    sys.stderr.write("Warning: Could not read status.\n\tDirectory: %r\n\tLog:%r\n" % (d, filename))
                else:
                    retval.append(retdict)
    return retval

def do_timestamp():
    print("""    <hr />
    <p>Report generated at %(timestamp)s.</p>""" % {"timestamp":datetime.datetime.now()})

def main():
    global args
    global HTML_DOC_HEAD
    global HTML_DOC_FOOT

    subs_dict = dict()
    subs_dict["report_title"] = args.title or HTML_DEFAULT_TITLE

    #Start output
    print(HTML_DOC_HEAD % subs_dict)
    #Make list of directories to summarize.
    geoproc_results_dirs = geoproc_library.get_results_dirs(args.results)
    #Build list of statuses
    stats = aggregate_statuses(geoproc_results_dirs)

    do_toc()
    do_processing_stats(stats)
    do_input_listing(geoproc_results_dirs)

    #Finish output
    do_timestamp()
    print(HTML_DOC_FOOT)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Summarize a results directory tree into an HTML report.")
    parser.add_argument("-d", "--debug", action="store_true", dest="debug", help="Enable debug printing (writes to stderr).")
    parser.add_argument('-r', '--regress', action='store_true', dest='regress', help='Run unit tests and exit.')
    args_regress = parser.parse_known_args()[0]

    #Run regression tests
    if args_regress.debug:
        sys.stderr.write("sys.argv: %r\n" % sys.argv)
    if args_regress.regress:
        sys.exit(0)

    parser.add_argument("-t", "--title", help="Specify HTML text for a one-line title of the report.  Defaults to %r." % HTML_DEFAULT_TITLE)
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output - do not summarize any of the script status lists.")
    parser.add_argument("results", help="Geoproc results of one or more images. Pass either a directory with results somewhere under it (such as the --output option of geoproc.sh), or a text file with the absolute paths to specific results to summarize, one path per line.")
    args = parser.parse_args()
    main()
