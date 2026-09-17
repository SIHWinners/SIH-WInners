-----------------------------------------------------------------------------
-- Function to overlap polygon on patch
--
CREATE OR REPLACE FUNCTION PC_Intersection(pcpatch, geometry)
	RETURNS pcpatch AS
	$$
		WITH
			 pts AS (SELECT @extschema@.PC_Explode($1) AS pt),
		   pgpts AS (SELECT @extschema@.ST_GeomFromEWKB(@extschema@.PC_AsBinary(pt)) AS pgpt, pt FROM pts),
			ipts AS (SELECT pt FROM pgpts WHERE @extschema@.ST_Intersects(pgpt, $2)),
			ipch AS (SELECT @extschema@.PC_Patch(pt) AS pch FROM ipts)
		SELECT pch FROM ipch;
	$$
	LANGUAGE 'sql';

-----------------------------------------------------------------------------
-- Cast from pcpatch to polygon
--
CREATE OR REPLACE FUNCTION PC_EnvelopeGeometry(pcpatch)
	RETURNS geometry AS
	$$
		SELECT @extschema@.ST_GeomFromEWKB(@extschema@.PC_EnvelopeAsBinary($1))
	$$
	LANGUAGE 'sql';

CREATE OR REPLACE FUNCTION geometry(pcpatch)
	RETURNS geometry AS
	$$
		SELECT @extschema@.PC_EnvelopeGeometry($1)
	$$
	LANGUAGE 'sql';



-----------------------------------------------------------------------------
-- Cast from pcpoint to point
--
CREATE OR REPLACE FUNCTION geometry(pcpoint)
	RETURNS geometry AS
	$$
		SELECT @extschema@.ST_GeomFromEWKB(@extschema@.PC_AsBinary($1))
	$$
	LANGUAGE 'sql';



-----------------------------------------------------------------------------
-- Function to overlap polygon on patch
--
CREATE OR REPLACE FUNCTION PC_Intersects(pcpatch, geometry)
	RETURNS boolean AS
	$$
		SELECT @extschema@.ST_Intersects($2, @extschema@.PC_EnvelopeGeometry($1))
	$$
	LANGUAGE 'sql';

CREATE OR REPLACE FUNCTION PC_Intersects(geometry, pcpatch)
	RETURNS boolean AS
	$$
		SELECT @extschema@.PC_Intersects($2, $1)
	$$
	LANGUAGE 'sql';

-----------------------------------------------------------------------------
-- Function from pcpatch to LineString
--
CREATE OR REPLACE FUNCTION PC_BoundingDiagonalGeometry(pcpatch)
	RETURNS geometry AS
	$$
		SELECT @extschema@.ST_GeomFromEWKB(@extschema@.PC_BoundingDiagonalAsBinary($1))
	$$
	LANGUAGE 'sql';

-----------------------------------------------------------------------------
-- Function returning the version number
--
CREATE OR REPLACE FUNCTION PC_PostGIS_Version()
	RETURNS text AS $$ SELECT '1.2.5'::text $$
	LANGUAGE 'sql' IMMUTABLE STRICT;
