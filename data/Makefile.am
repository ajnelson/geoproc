pkgdata_DATA = location_ground_truth.db known_locations.csv
EXTRA_DIST = known_locations.csv

# The top_srcdir was found necessary to have `make distcheck` pass.
location_ground_truth.db: $(top_srcdir)/python/create_location_ground_truth.py $(top_srcdir)/data/known_locations.csv
	python3 $(top_srcdir)/python/create_location_ground_truth.py -z $(top_srcdir)/data/known_locations.csv location_ground_truth.db

DISTCLEANFILES=$(pkgdata_DATA)
