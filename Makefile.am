SUBDIRS = doc deps etc python data src tests
EXTRA_DIST = vchead bootstrap.sh .gitignore .gitmodules

pkgdata_DATA = vchead

vchead: FORCE
	@if [ -d .git ]; then \
	  echo "git:`git rev-parse HEAD`">vchead; \
	else \
	  if [ ! -r vchead ]; then \
	    echo "date:`date`">vchead; \
	  fi \
	fi

# Force vchead target to be re-made on every make invocation
FORCE:

DISTCLEANFILES = $(pkgdata_DATA)
