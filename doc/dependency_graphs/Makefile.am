pkgdocdir = $(pkgdatadir)/doc
dist_pkgdoc_DATA = \
  analyze_cookie_files.pdf \
  analyze_email_files.pdf \
  analyze_exif_headers.pdf \
  analyze_ipv4s.pdf \
  analyze_cookie_files.png \
  analyze_email_files.png \
  analyze_exif_headers.png \
  analyze_ipv4s.png

EXTRA_DIST = \
  analyze_cookie_files.gv \
  analyze_email_files.gv \
  analyze_exif_headers.gv \
  analyze_ipv4s.gv

%.png: %.gv
	dot -Tpng -o$@ $<

%.pdf: %.gv
	dot -Tpdf -o$@ $<
