#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.68])
AC_INIT(geoproc, 0.0.1, ajnelson@cs.ucsc.edu)
AM_INIT_AUTOMAKE(geoproc,0.0.1)

# Checks for programs.
AC_PROG_YACC
AC_PROG_LEX
AC_PROG_INSTALL
AC_PROG_MAKE_SET

# Check for GNU versions of some programs: getopt and readlink
#TODO Check for other BSDs
if test "$(uname -s)" = "Darwin"; then
  AC_CHECK_PROG(HAVE_GETOPT,getopt,yes,,/opt/local/bin)
  if test "$HAVE_GETOPT" = "yes"; then
    AC_SUBST(GNU_GETOPT,/opt/local/bin/getopt)
  else
    AC_MSG_ERROR([OS X environment detected, but GNU getopt not found; please install the MacPort package 'getopt'.  The BSD getopt included with OS X is known to be problematic.])
  fi
else
  AC_CHECK_PROG(HAVE_GETOPT,getopt,yes)
  if test "$HAVE_GETOPT" = "yes"; then
    AC_SUBST(GNU_GETOPT,getopt)
  else
    AC_MSG_ERROR([GNU getopt not found.])
  fi
fi

# Check for Python 2 _and_ Python 3
dnl Populates variables for Python 3 analagous to variables listed here: <http://www.gnu.org/savannah-checkouts/gnu/automake/manual/html_node/Python.html>
AM_PATH_PYTHON(3.2)
AC_SUBST(PYTHON3,$PYTHON)
AC_SUBST(HAVE_PYTHON3,$HAVE_PYTHON)
AC_SUBST(PYTHON3_VERSION,$PYTHON_VERSION)
AC_SUBST(PYTHON3_PREFIX,$PYTHON_PREFIX)
AC_SUBST(PYTHON3_EXEC_PREFIX,$PYTHON_EXEC_PREFIX)
AC_SUBST(PYTHON3_PLATFORM,$PYTHON_PLATFORM)
AC_SUBST(python3dir,$pythondir)
AC_SUBST(pkgpython3dir,$pkgpythondir)
AC_SUBST(py3execdir,$pyexecdir)
AC_SUBST(pkgpy3execdir,$pkgpyexecdir)

dnl Unfortunately this then just uses the cached values from above...
dnl TODO AM_PATH_PYTHON(2.7)

AC_CHECK_PROG(HAVE_ICAT,icat,yes)
if test "$HAVE_ICAT" != "yes"; then
  AC_MSG_ERROR([icat not found; refer to INSTALL for SleuthKit compilation notes.])
fi

AC_CHECK_PROG(HAVE_FIWALK,fiwalk,yes)
if test "$HAVE_FIWALK" != "yes"; then
  AC_MSG_ERROR([fiwalk not found; refer to INSTALL for SleuthKit compilation notes.])
fi

AC_CHECK_PROG(HAVE_BULK_EXTRACTOR,bulk_extractor,yes)
if test "$HAVE_BULK_EXTRACTOR" != "yes"; then
  AC_MSG_ERROR([bulk_extractor not found; refer to INSTALL for bulk_extractor compilation notes.])
fi

AC_CHECK_PROG(HAVE_READPST,readpst,yes)
if test "$HAVE_READPST" != "yes"; then
  AC_MSG_ERROR([readpst not found; install libpst.])
fi

dnl This doesn't have to be an error, some sensible default can be chosen.
dnl AC_CHECK_PROG(HAVE_MPSTAT,mpstat,yes)
dnl if test "$HAVE_MPSTAT" != "yes"; then
dnl   AC_MSG_ERROR([mpstat not found; please install its containing package, usually 'sysstat'.])
dnl else
dnl   num_cores_on_this_box=$(($(mpstat -P ALL | wc -l) - 4))
dnl fi

dnl TODO Check for other tests to run later (e.g. run database tests)
dnl <http://stackoverflow.com/a/6504734/1207160>

# Checks for libraries.

# Checks for header files.

# Checks for typedefs, structures, and compiler characteristics.

# Checks for library functions.

AC_CONFIG_FILES([Makefile
                 data/Makefile
                 deps/Makefile
                 doc/Makefile
                 doc/dependency_graphs/Makefile
                 etc/Makefile
                 python/geoproc_cfg.py
                 python/Makefile
                 src/geoproc.sh
                 src/Makefile
                 src/mysql_setup/Makefile
                 src/process/analyze_cookie_files.sh
                 src/process/analyze_email_files.sh
                 src/process/analyze_exif_headers.sh
                 src/process/analyze_ipv4s.sh
                 src/process/check_bulk_extractor.sh
                 src/process/check_dependencies.sh
                 src/process/do_bulk_extractor.sh
                 src/process/do_identify_filenames.sh
                 src/process/extract_cookie_files.sh
                 src/process/extract_email_files.sh
                 src/process/fetch_location_lists.sh
                 src/process/make_kml.sh
                 src/process/make_reconstructed_emailheaders.sh
                 src/process/make_reconstructed_httpheaders.sh
                 src/process/verify_fiwalk_versus_tsk_db.sh
                 src/process/verify_tsk_db.sh
                 src/process/geoproc.mk
                 src/process/Makefile
                 tests/Makefile])

# Generate some files that require executable permission (namely unit tests)
# (Suggested on multiple help sites, one example: <http://stackoverflow.com/a/11417586/1207160>)
AC_CONFIG_FILES([src/geoproc_process.sh], [chmod +x src/geoproc_process.sh])
AC_CONFIG_FILES([src/geoproc_test_conn.sh], [chmod +x src/geoproc_test_conn.sh])
AC_CONFIG_FILES([tests/test_aggregate.sh], [chmod +x tests/test_aggregate.sh])
AC_CONFIG_FILES([tests/test_argparse.sh], [chmod +x tests/test_argparse.sh])
AC_CONFIG_FILES([tests/test_analyze_cookie_files.sh], [chmod +x tests/test_analyze_cookie_files.sh])
AC_CONFIG_FILES([tests/test_analyze_exif_headers.sh], [chmod +x tests/test_analyze_exif_headers.sh])
AC_CONFIG_FILES([tests/test_dfxml.sh], [chmod +x tests/test_dfxml.sh])
AC_CONFIG_FILES([tests/test_geoproc_library.sh], [chmod +x tests/test_geoproc_library.sh])
AC_CONFIG_FILES([tests/test_make_kml.sh], [chmod +x tests/test_make_kml.sh])
AC_CONFIG_FILES([tests/test_reconstruct.sh], [chmod +x tests/test_reconstruct.sh])
AC_CONFIG_FILES([tests/test_geoproc_cfg.sh], [chmod +x tests/test_geoproc_cfg.sh])
AC_CONFIG_FILES([tests/test_geoproc_commands.sh], [chmod +x tests/test_geoproc_commands.sh])

AC_OUTPUT
