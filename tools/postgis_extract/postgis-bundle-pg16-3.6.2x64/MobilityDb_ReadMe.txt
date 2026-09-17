## INTRODUCTION
MobilityDB is a geospatial trajectory data management & analysis platform, built on PostgreSQL and PostGIS
This package is for PostGIS 3.6 series
More details can be found at: https://github.com/MobilityDB/MobilityDB

## INSTALL
To install first create a postgresql database using createdb, psql, or pgAdmin
Copy the files from this zip file to same named folders in your PostgreSQL install.

Make sure you've already installed PostGIS binaries, via stackbuilder 
or downloads listed from https://postgis.net/documentation/getting_started/install_windows/unreleased_versions/

In your system add postgis-3 and change max_locks_per_transaction to the preload section of your postgresql.conf, or alternatively from psql 

```
-- confirm you don't have any existing pre-loaded libraries, 
-- if you do make sure to readd when alter system
SHOW shared_preload_libraries;
ALTER SYSTEM  SET shared_preload_libraries = 'postgis-3';

SHOW max_locks_per_transaction;

-- if lower than 128, then run the below 
ALTER SYSTEM SET max_locks_per_transaction = 128;
```

From Windows services, restart the PostgreSQL service.



Install PostGIS using:
CREATE EXTENSION postgis;

Then install mobilitydb:

CREATE EXTENSION mobilitydb;


If updating from old pgrouting use instead
ALTER EXTENSION mobilitydb UPDATE;
