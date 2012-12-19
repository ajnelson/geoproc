installcheckdir = ${pkgdatadir}/tests

check_SCRIPTS = \
  test_aggregate.sh \
  test_argparse.sh \
  test_analyze_cookie_files.sh \
  test_analyze_exif_headers.sh \
  test_dfxml.sh \
  test_geoproc_cfg.sh \
  test_geoproc_library.sh \
  test_make_kml.sh \
  test_reconstruct.sh

installcheck_SCRIPTS = \
  test_geoproc_commands.sh

TESTS = $(check_SCRIPTS)

INSTALLTESTS = $(installcheck_SCRIPTS)

EXTRA_DIST = \
  $(check_SCRIPTS) \
  $(installcheck_SCRIPTS)
