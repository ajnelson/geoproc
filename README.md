# GeoProc

This README provides an overview of GeoProc, configuration instructions, and usage examples.

## Overview

GeoProc is a forensic workflow that attempts to determine the locations of use of a disk image.  Given a disk image, the end result is a KML file describing all found locations, including notes on the previously-observed precision of each indicative artifact (when available).

GeoProc makes use of low-level content extractors, [The Sleuth Kit](https://github.com/sleuthkit/sleuthkit) and [Bulk Extractor](https://github.com/simsong/bulk_extractor), for file system and pattern-matching content.  Bash and Python scripts then further process the extracted content to draw conclusions from extracted artifacts that indicate location.

The progression of data analysis is non-linear.  For example, an email address found in plain text from Bulk Extractor's pattern matching may be a part of a file.  The output from Bulk Extractor often has a byte address, so if The Sleuth Kit could successfuly parse the image's file systems, the email address can then be attributed to a file based on the file systems' sector allocation tables.  Unfortunately, file systems are not guaranteed to be parseable.

To resolve issues with partial processing, GeoProc breaks the analysis into small, specialized programs that analyze or transform data step-wise, similar to data mining suites (such as SAS or SPSS).  The programs are run in parallel according to their dependency graph; for instance, a file extractor depends on the file system metadata being extracted first.  The output of each program is contained within a directory specific to only it, and each directory has associated logs for:

* Standard out (`.out.log`)
* Standard error (`.err.log`)
* Exit status (`.status.log`)
* Version of GeoProc used at script run-time (`.version.log`)

In event of an error or unexpected results, this allows one to delete the erroneous results and re-run part of an analysis.  Results that depended on something that failed exit in a special status that indicates they should be attempted on the next invocation of GeoProc.

## Installation

See the INSTALL file.  The project basically builds with `./configure && make && make install`, but it relies on several utilities that have their own dependencies.

This README uses the term `$prefix` in file system paths to indicate the installation prefix.  This is usually `/usr` or `/usr/local` on a system-wide installation.

## Usage

To see the full list of command-line interface options for any of the commands, run `geoproc.sh` without any arguments, or with the `-h` flag.

After running GeoProc, the main results are stored in two files, in the directory `$output_root/$disk_image_full_path/`:

* `index.html` - A summary of location beliefs and the processing status (success/failure indicators) of the component scripts.
* `make_kml.sh/all.kml` - A KML file mapping all location artifacts, grouping by precise lat/long pairs.

A little setup is required before running, mainly for database details.

### Setting up GeoProc for processing

The setup to analyze a single disk image occurs in multiple phases.  

#### Configuring

See the source file `etc/geoproc.cfg` (which is installed to `$prefix/share/geoproc/geoproc.cfg`), and copy it to `~/geoproc.cfg` if you wish to change anything.

There are two basic configuration needs:
* The analysis scripts depend on connectivity to a MySQL database.  This is to query data that map IP addresses to geographic locations, and determine names of locations.  
* You may want to configure the limit of how many CPU cores GeoProc will use concurrently.  Rest assured that at least Bulk Extractor will use all the CPU you offer it.

#### Testing connectivity

To test your database connection, run this command:

    geoproc.sh test_conn

### Processing a single disk image

This command invokes the processing graph.

    geoproc.sh process $disk_image

You can run the 'process' action multiple times on the same disk image, though you should not do these runs simultaneously.  You may want to do multiple runs if you find that some script has a correctible bug.

Among its available options are specifying a particular script you wish to run.  For instance, you may want to run Bulk Extractor by itself and give it all the CPU power available, followed by a parallel processing of the rest of the dependency graph.  (Currently, Bulk Extractor is the only multi-core process.  The rest are single-core.)  To do this, first invoke the `process` command by targeting the `check_bulk_extractor.sh` script, which re-runs Bulk Extractor with a reduced scanner set if the modified version fails.

    geoproc.sh process --target-script=check_bulk_extractor.sh $disk_image

Then the rest of the graph can be run.

    geoproc.sh process $disk_image

### Processing many disk images

If you are constrained to using only a single machine, it is still possible to process a corpus of disk images in parallel.  The rest of this subsection is an example parallel processing workflow, previously used to analyze over two thousand disk images on a single machine.

Since Bulk Extractor is massively parallel by itself, parallel processing should occur in three phases: Image verification, Bulk Extractor, and then the rest of the graph.

First, the example machine happens to have 24 processing cores, so the corpus list is split into 23 parts (leaving one core for non-work use; IO-boundedness usually keeps the cores from being entirely pegged).  The file `src/split_worklist.sh` (installed to `$prefix/share/geoproc/scripts/split_worklist.sh`) is a small utility script that randomly splits the corpus list.  For example, splitting the file `corpuslist.txt` into 23 random subsets:

    $prefix/share/geoproc/scripts/split_worklist.sh 23 corpuslist.txt

Next, verification of disk images is not a parallel task, so the first parallel step can occur now.  A Bash loop backgrounds as many sequential processing script loops as you've split the worklist into.

    for x in $(ls sorted_split23_corpuslist.txt_*); do
      while read y; do
        echo $(date) $y;
        geoproc.sh process --target-script=verify_disk_image.sh "$y";
      done<$x &
    done;

Now, the Bulk Extractor runs can happen in sequence.

    while read y; do
      echo $(date) $y;
      geoproc.sh process --target-script=check_bulk_extractor.sh "$y";
    done<corpus_list.txt

Finally, the rest of the graph can be executed.

    for x in $(ls sorted_work23_corpus_list_*); do
      while read y; do
        echo $(date) $y;
        geoproc.sh process "$y";
      done<$x &
    done;

### Aggregate analysis and revising precision data

If you want to produce your own beliefs on artifacts' precision, follow the instructions in this section.

First, you must aggregate the results of GeoProc runs, on which you wish to base your precision measurements, into a single database file.  An example command is:

    geoproc.sh aggregate /path/to/processing/output/root corpus-aggregate.db

The precision information is derived from `data/known_locations.csv`.  If you modify this CSV, re-run `make` and `make install`, and then `geoproc.sh aggregate` will recognize the updated ground truth.

After producing the aggregate database, create the precision database with:

    geoproc.sh evaluate_precision corpus-aggregate.db corpus-precision.db

The `process` GeoProc command accepts this precision database with the `--precision-db` option.

## Reference

### Processing scripts

The workflow scripts' dependencies are illustrated in `doc/dependency_graphs/`.

### Exit statuses

The `summarize` command produces a table of exit statuses of the scripts of GeoProc.  Here are what the more common values mean:

* 0: No failure.
* 11: This script can be tried again. Either some required script didn't run successfully, or the database connection was needed but unavailable.  Re-running geoproc.sh will by default remove all output from scripts that exited in this status and re-run them.
* 143: Script aborted (somebody killed this script, probably because it was running too long).

Other statuses require reviewing the log files for interpretation.
