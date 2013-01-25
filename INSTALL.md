## Building

Currently, the build process assumes starting from a fresh installation of one of a few Unix-like distros.  The process is:

 * Install dependent packages for your platform.
 * Build and install the specifically-versioned programs GeoProc uses.
 * Build and install GeoProc.

### Dependent packages

Packages can be installed with the appropriate script `deps/install_dependent_packages-(your distro).sh`.  GeoProc was developed in Fedora and Mac OS X, and is being tested in Ubuntu.  Other distros are not currently supported.

### Dependent programs

This section is only necessary if you want to test a custom version of Bulk Extractor that is not yet integrated into the GeoProc results.

To build and install programs that have specific versions tracked by Git submodule, there is a script `deps/build_submodules.sh` that makes these dependencies.  First, download them by executing the following in the GeoProc top source directory:

    git submodule init
    git submodule update

There are two choices on installing the utilities:

 * If you are willing to augment your shell's PATH variables to include the `~/local` prefix, run `deps/build_submodules.sh local [prefix_directory]`; `prefix_directory` is optional and defaults to `$HOME/local`.  The file `deps/bashrc` includes the specific path augmentations that make this work; appending this file to your own `~/.bashrc` is sufficient (though don't forget to refresh your environment with `source ~/.bashrc` when you modify your `~/.bashrc` file).
 * If you would rather install these utilities system-wide, run `deps/build_submodules.sh system`.
 
After building, this command should show an options list:

    icat

Until GeoProc is packaged properly for `yum`, `apt-get` or `port` installations, the `local` option is recommended.

### GeoProc

GeoProc can be built with:

    ./bootstrap.sh && ./configure && make && sudo make install

Until GeoProc is added to package managers, you may prefer a local installation (adding `export PATH=$HOME/local/bin:$PATH` to your `~/.bashrc` is sufficient to run this like other programs):

    ./bootstrap.sh && ./configure --prefix=$HOME/local && make && make install

## Setting up the database

To build a development or testing database, GeoProc includes a minimal setup script you can run after building a MySQL server and securing it as desired (e.g. starting with `mysql_secure_installation`).  To populate it, the built GeoProc program includes a command that can load any number of months of MaxMind IP-location data.

### Creating the database

The GeoProc command `geoproc.sh build_ip_tables` populates a MySQL database with IP address location mappings.  Setting up a fresh MySQL installation is beyond the scope of this documentation, but once things are generally up and running, you can use the `maxmind_minimal_setup.sql` script to set up the last schema details:

    mysql -p -u root <src/mysql_setup/maxmind_minimal_setup.sql

Note that those SQL instructions are sufficient for a development or testing environment, but a production server will likely have more stringent security requirements that this documentation cannot foresee.

### Populating the database

The database is populated with content provided by MaxMind.  Download at least the most recent [GeoLite city](https://geolite.maxmind.com/download/geoip/database/GeoLiteCity_CSV/) data, though you can download as many months of data as you wish.  Download zip files, but do not unpack them (GeoProc uses time stamps contained in the zip files).  The `build_ip_tables` command builds the database tables if needed, and loads any data not yet in the database.  Note that you will need the database connection config file (`etc/geoproc.cfg`) in place (copied to `~/geoproc.cfg` and edited to your liking, though its default contents match this documenation).

At the moment, the populating action requires database configuration files similar to the rest of GeoProc, so the rest of GeoProc needs to first be built.  In the future this will require only a reduced configuration file and could run without needing to build everything else.

## Testing and developing

A suite of regression tests is built into the workflow's programs.  Every build is tested from source with the following commands:

    ./bootstrap.sh && ./configure --prefix=$PWD/build && make && make check && make distcheck && make install && build/bin/geoproc.sh test_conn -d && echo "Build successful."

This builds the code, installs into a local directory, runs all the regression tests, and tests the database connection.

If you wish to add your own scripts to the workflow, it is easiest to follow by example of other scripts that are already a part of the workflow.  Issuing this in the GeoProc top source directory should give a sufficient idea of what's needed to insert your own component script:

    grep -R 'analyze_email_files.sh' *

## Troubleshooting

If, while building the git-tracked projects, you are encountering errors with libewf symbols not being found, check if you have a libewf package installed *and* you have libewf installed under your local prefix (e.g. `$HOME/local/include/libewf.h` exists).  This confuses the compiler and linker and causes the build to fail.  On Fedora, you can check for the installed package with `yum list installed | grep ewf`.
