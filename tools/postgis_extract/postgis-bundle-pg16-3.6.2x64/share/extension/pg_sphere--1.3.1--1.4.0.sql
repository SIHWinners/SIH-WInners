-- add "fetch" support function to enable index-only scans for spoint3

-- g_spoint3_fetch was already part of the spoint3 opclass in older versions
-- around 1.0, but later made optional (see bdc37d1)

DO $$
BEGIN
   ALTER OPERATOR FAMILY spoint3 USING gist ADD
      FUNCTION 9 (spoint, spoint) g_spoint3_fetch (internal);
EXCEPTION
   WHEN duplicate_object THEN NULL;
   WHEN OTHERS THEN RAISE;
END;
$$;

-- remove legacy spellings of operators
DROP OPERATOR IF EXISTS @(bigint, smoc);
DROP OPERATOR IF EXISTS @(spoint, smoc);

-- add spoly function that takes an array of float8 values in radians
CREATE FUNCTION spoly(float8[])
   RETURNS spoly
   AS 'MODULE_PATHNAME', 'spherepoly_rad'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoly(float8[]) IS
   'creates spoly from array of numbers in radians';

CREATE FUNCTION spoly(spoint[])
  RETURNS spoly
  AS 'MODULE_PATHNAME', 'spherepoly_from_point_array'
  LANGUAGE 'c'
  IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoly(spoint[]) IS
  'creates spoly from an array of points';

-- add PARALLEL SAFE to spoly_deg(float8[])
ALTER FUNCTION spoly_deg(float8[]) IMMUTABLE STRICT PARALLEL SAFE;

-- update comment on spoly_deg function
COMMENT ON FUNCTION spoly_deg(float8[]) IS
   'creates spoly from array of numbers in degrees';
CREATE FUNCTION spoint_contained_by_circle_sel(internal, oid, internal, integer)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_sel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_sel(internal, oid, internal, integer) IS
   'selectivity estimator function for spoint_contained_by_circle';

CREATE FUNCTION spoint_contained_by_circle_joinsel(internal, oid, internal, smallint, internal)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_joinsel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_joinsel(internal, oid, internal, smallint, internal) IS
   'join selectivity estimator function for spoint_contained_by_circle';


CREATE FUNCTION spoint_contained_by_circle_neg_sel(internal, oid, internal, integer)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_neg_sel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_neg_sel(internal, oid, internal, integer) IS
   'selectivity estimator function for spoint_contained_by_circle_neg';

CREATE FUNCTION spoint_contained_by_circle_neg_joinsel(internal, oid, internal, smallint, internal)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_neg_joinsel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_neg_joinsel(internal, oid, internal, smallint, internal) IS
   'join selectivity estimator function for spoint_contained_by_circle_neg';


CREATE FUNCTION spoint_contained_by_circle_com_sel(internal, oid, internal, integer)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_com_sel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_com_sel(internal, oid, internal, integer) IS
   'selectivity estimator function for spoint_contained_by_circle_com';

CREATE FUNCTION spoint_contained_by_circle_com_joinsel(internal, oid, internal, smallint, internal)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_com_joinsel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_com_joinsel(internal, oid, internal, smallint, internal) IS
   'join selectivity estimator function for spoint_contained_by_circle_com';


CREATE FUNCTION spoint_contained_by_circle_com_neg_sel(internal, oid, internal, integer)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_com_neg_sel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_com_neg_sel(internal, oid, internal, integer) IS
   'selectivity estimator function for spoint_contained_by_circle_com_neg';

CREATE FUNCTION spoint_contained_by_circle_com_neg_joinsel(internal, oid, internal, smallint, internal)
   RETURNS double precision
   AS 'MODULE_PATHNAME' , 'spherepoint_in_circle_com_neg_joinsel'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_contained_by_circle_com_neg_joinsel(internal, oid, internal, smallint, internal) IS
   'join selectivity estimator function for spoint_contained_by_circle_com_neg';


ALTER OPERATOR @> (scircle, spoint)
SET (
   RESTRICT   = spoint_contained_by_circle_com_sel,
   JOIN       = spoint_contained_by_circle_com_joinsel
);

ALTER OPERATOR <@ (spoint, scircle)
SET (
   RESTRICT   = spoint_contained_by_circle_sel,
   JOIN       = spoint_contained_by_circle_joinsel
);

ALTER OPERATOR !@> (scircle, spoint)
SET (
   RESTRICT   = spoint_contained_by_circle_com_neg_sel,
   JOIN       = spoint_contained_by_circle_com_neg_joinsel
);

ALTER OPERATOR !<@ (spoint, scircle)
SET (
   RESTRICT   = spoint_contained_by_circle_neg_sel,
   JOIN       = spoint_contained_by_circle_neg_joinsel
);


CREATE FUNCTION spoint_dwithin(spoint, spoint, float8)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spherepoint_dwithin'
   LANGUAGE C
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_dwithin(spoint, spoint, float8) IS
   'predicate matching spherical points less than a given distance apart';
CREATE FUNCTION spoint_hash32 (spoint)
   RETURNS int
   IMMUTABLE STRICT
   PARALLEL SAFE
   LANGUAGE C
   AS 'MODULE_PATHNAME', 'spherepoint_hash32';

UPDATE pg_operator
   SET oprcanhash = true
   WHERE oprname = '=' AND
     oprleft = 'spoint'::regtype AND oprright = 'spoint'::regtype;

/* PG17: ALTER OPERATOR = (spoint, spoint) SET (HASHES); */

CREATE OPERATOR CLASS spoint_hash_ops
   DEFAULT FOR TYPE spoint USING hash
   AS
      OPERATOR 1 = (spoint, spoint),
      FUNCTION 1 spoint_hash32(spoint);
-- PG12+ has support functions

CREATE FUNCTION spoint_dwithin_supportfn (internal)
        RETURNS internal
        AS 'MODULE_PATHNAME', 'spherepoint_dwithin_supportfn'
        LANGUAGE 'c';

COMMENT ON FUNCTION spoint_dwithin_supportfn(internal) IS
   'support function for spoint_dwithin';

ALTER FUNCTION spoint_dwithin(spoint, spoint, float8)
   SUPPORT spoint_dwithin_supportfn;
