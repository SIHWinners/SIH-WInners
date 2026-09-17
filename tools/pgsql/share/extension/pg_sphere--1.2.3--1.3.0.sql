CREATE FUNCTION scircle_deg(spoint, float8)
   RETURNS scircle
   AS 'MODULE_PATHNAME' , 'spherecircle_by_center_deg'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION scircle_deg(spoint, float8) IS
  'spherical circle with spherical point as center and float8 as radius in degrees';

CREATE FUNCTION spoint_deg(FLOAT8, FLOAT8)
   RETURNS spoint
   AS 'MODULE_PATHNAME', 'spherepoint_from_long_lat_deg'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION spoint_deg(FLOAT8, FLOAT8) IS
  'returns a spherical point from longitude (arg1, in degrees), latitude (arg2, in degrees)';

CREATE FUNCTION spoly_deg(float8[])
   RETURNS spoly
   AS 'MODULE_PATHNAME', 'spherepoly_deg'
   LANGUAGE 'c'
   IMMUTABLE STRICT;

COMMENT ON FUNCTION spoly_deg(float8[]) IS
   '   Create spoly from array of points.
   Two consecutive numbers among those present
   refer to the same occurrence and cover its
   latitude and longitude, respectively.';

CREATE FUNCTION spath_as_array(spath)
   RETURNS spoint[]
   AS 'MODULE_PATHNAME', 'spherepath_get_array'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION  spath_as_array(spath) IS
  'returns spath as array of points';

CREATE FUNCTION spoint(spoly, int4)
   RETURNS spoint
   AS 'MODULE_PATHNAME', 'spherepoly_get_point'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION  spoint(spoly, int4) IS
  'returns n-th point of spherical polygon';

CREATE FUNCTION spoly_as_array(spoly)
   RETURNS spoint[]
   AS 'MODULE_PATHNAME', 'spherepoly_get_array'
   LANGUAGE 'c'
   IMMUTABLE STRICT PARALLEL SAFE;

COMMENT ON FUNCTION  spoly_as_array(spoly) IS
  'returns spoly as array of points';

CREATE FUNCTION dist(sline, spoint)
   RETURNS FLOAT8
   AS 'MODULE_PATHNAME', 'sphereline_point_distance'
   LANGUAGE 'c'
   IMMUTABLE STRICT;

COMMENT ON FUNCTION dist(sline, spoint) IS
  'returns the distance between spherical line and spherical point';

CREATE OPERATOR  <-> (
   LEFTARG    = sline,
   RIGHTARG   = spoint,
   COMMUTATOR = '<->',
   PROCEDURE  = dist
);

COMMENT ON OPERATOR <-> (sline, spoint) IS
  'returns the distance between spherical line and spherical point';

CREATE FUNCTION dist(spoint, sline)
   RETURNS FLOAT8
   AS 'MODULE_PATHNAME', 'sphereline_point_distance_com'
   LANGUAGE 'c'
   IMMUTABLE STRICT;

COMMENT ON FUNCTION dist(spoint, sline) IS
  'returns the distance between spherical line and spherical point';


CREATE OPERATOR  <-> (
   LEFTARG    = spoint,
   RIGHTARG   = sline,
   COMMUTATOR = '<->',
   PROCEDURE  = dist
);

COMMENT ON OPERATOR <-> (spoint, sline) IS
  'returns the distance between spherical line and spherical point';

CREATE FUNCTION spoly_is_convex(spoly)
   RETURNS BOOL
   AS 'MODULE_PATHNAME', 'spherepoly_is_convex'
   LANGUAGE 'c'
   IMMUTABLE PARALLEL SAFE;

COMMENT ON FUNCTION spoly_is_convex(spoly) IS
  'true if spherical polygon is convex';

--------------------------------------------------------------------
-- BRIN support                                                   --
--------------------------------------------------------------------

--------------------------------
-- the Operators              --
--------------------------------

CREATE FUNCTION spoint_overlaps_spherekey(spoint, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spoint_overlaps_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION spoint_contains_spherekey(spoint, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spoint_contains_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION spoint_iscontained_spherekey(spoint, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spoint_iscontained_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION sbox_overlaps_spherekey(sbox, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'sbox_overlaps_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION sbox_contains_spherekey(sbox, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'sbox_contains_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION sbox_iscontained_spherekey(sbox, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'sbox_iscontained_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION spherekey_overlaps_spherekey(spherekey, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spherekey_overlaps_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION spherekey_contains_spherekey(spherekey, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spherekey_contains_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE FUNCTION spherekey_iscontained_spherekey(spherekey, spherekey)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spoint_iscontained_spherekey'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE OPERATOR && (
   LEFTARG    = spoint,
   RIGHTARG   = spherekey,
   PROCEDURE  = spoint_overlaps_spherekey,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (spoint, spherekey) IS
  'true, if the spherical point overlaps a spherekey';

CREATE OPERATOR @> (
   LEFTARG    = spoint,
   RIGHTARG   = spherekey,
   PROCEDURE  = spoint_contains_spherekey,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR @> (spoint, spherekey) IS
  'true, if the spherical point contains a spherekey - just needed to define the OpFamily';

CREATE OPERATOR <@ (
   LEFTARG    = spoint,
   RIGHTARG   = spherekey,
   PROCEDURE  = spoint_iscontained_spherekey,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR <@ (spoint, spherekey) IS
  'true, if the spherical point is contained in a spherekey';

CREATE OPERATOR && (
   LEFTARG    = sbox,
   RIGHTARG   = spherekey,
   PROCEDURE  = sbox_overlaps_spherekey,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (sbox, spherekey) IS
  'true, if the spherical box overlaps a spherekey';

CREATE OPERATOR @> (
   LEFTARG    = sbox,
   RIGHTARG   = spherekey,
   PROCEDURE  = sbox_contains_spherekey,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR @> (sbox, spherekey) IS
  'true, if the spherical box contains a spherekey';

CREATE OPERATOR <@ (
   LEFTARG    = sbox,
   RIGHTARG   = spherekey,
   PROCEDURE  = sbox_iscontained_spherekey,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR <@ (sbox, spherekey) IS
  'true, if the spherical box is contained in a spherekey';

CREATE OPERATOR && (
   LEFTARG    = spherekey,
   RIGHTARG   = spherekey,
   PROCEDURE  = spherekey_overlaps_spherekey,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (spherekey, spherekey) IS
  'true, if the spherekey overlaps another spherekey';

CREATE OPERATOR @> (
   LEFTARG    = spherekey,
   RIGHTARG   = spherekey,
   PROCEDURE  = spherekey_contains_spherekey,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR @> (spoint, spherekey) IS
  'true, if the spherekey contains another spherekey';

CREATE OPERATOR <@ (
   LEFTARG    = spherekey,
   RIGHTARG   = spherekey,
   PROCEDURE  = spherekey_iscontained_spherekey,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR <@ (spherekey, spherekey) IS
  'true, if the spherical point is contained in another spherekey';

---------------------------------------------
-- create operators with crossed datatypes --
---------------------------------------------

CREATE FUNCTION spherekey_overlaps_spoint(spherekey, spoint)
   RETURNS boolean
   AS $$
     SELECT $2 && $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE FUNCTION spherekey_contains_spoint(spherekey, spoint)
   RETURNS boolean
   AS $$
     SELECT $2 <@ $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE FUNCTION spherekey_iscontained_spoint(spherekey, spoint)
   RETURNS boolean
   AS $$
     SELECT $2 @> $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE FUNCTION spherekey_overlaps_sbox(spherekey, sbox)
   RETURNS boolean
   AS $$
     SELECT $2 && $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE FUNCTION spherekey_contains_sbox(spherekey, sbox)
   RETURNS boolean
   AS $$
     SELECT $2 <@ $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE FUNCTION spherekey_iscontained_sbox(spherekey, sbox)
   RETURNS boolean
   AS $$
     SELECT $2 @> $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE OPERATOR && (
   LEFTARG    = spherekey,
   RIGHTARG   = spoint,
   PROCEDURE  = spherekey_overlaps_spoint,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (spherekey, spoint) IS
  'true, if the spherekey overlaps a spoint';

CREATE OPERATOR @> (
   LEFTARG    = spherekey,
   RIGHTARG   = spoint,
   PROCEDURE  = spherekey_contains_spoint,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR @> (spherekey, spoint) IS
  'true, if the spherekey contains a spherical point';

CREATE OPERATOR <@ (
   LEFTARG    = spherekey,
   RIGHTARG   = spoint,
   PROCEDURE  = spherekey_iscontained_spoint,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR <@ (spherekey, spoint) IS
  'true, if the spherekey is contained in a spherical point - just needed to define the OpFamily';

CREATE OPERATOR && (
   LEFTARG    = spherekey,
   RIGHTARG   = sbox,
   PROCEDURE  = spherekey_overlaps_sbox,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (spherekey, sbox) IS
  'true, if the spherekey overlaps a spherical point';

CREATE OPERATOR @> (
   LEFTARG    = spherekey,
   RIGHTARG   = sbox,
   PROCEDURE  = spherekey_contains_sbox,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR @> (spherekey, sbox) IS
  'true, if the spherekey contains a spherical point';

CREATE OPERATOR <@ (
   LEFTARG    = spherekey,
   RIGHTARG   = sbox,
   PROCEDURE  = spherekey_iscontained_sbox,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR <@ (spherekey, sbox) IS
  'true, if the spherekey is contained in a spherical point';

-------------------------------------------------
-- create operators that will actually be used --
-------------------------------------------------

CREATE FUNCTION spoint_overlaps_sbox(spoint, sbox)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'spoint_overlaps_sbox'
   LANGUAGE 'c'  IMMUTABLE STRICT;

CREATE OPERATOR && (
   LEFTARG    = spoint,
   RIGHTARG   = sbox,
   PROCEDURE  = spoint_overlaps_sbox,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (spoint, sbox) IS
  'true, if the spherical point overlaps a spherical box';

------------------------------------------------------------
-- Complementar operators, needed for OpFamily definition --
------------------------------------------------------------

CREATE FUNCTION sbox_overlaps_spoint(sbox, spoint)
   RETURNS boolean
   AS $$
     SELECT $2 && $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE OPERATOR && (
   LEFTARG    = sbox,
   RIGHTARG   = spoint,
   PROCEDURE  = sbox_overlaps_spoint,
   COMMUTATOR = '&&',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

COMMENT ON OPERATOR && (sbox, spoint) IS
  'true, if the spherical box overlaps a spherical point';

CREATE FUNCTION sbox_iscontained_spoint(sbox, spoint)
   RETURNS boolean
   AS 'MODULE_PATHNAME', 'sbox_iscontained_spoint'
   LANGUAGE 'c'  IMMUTABLE STRICT; 

CREATE OPERATOR <@ (
   LEFTARG    = sbox,
   RIGHTARG   = spoint,
   PROCEDURE  = sbox_iscontained_spoint,
   COMMUTATOR = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

CREATE FUNCTION spoint_contains_sbox(spoint, sbox)
   RETURNS boolean
   AS $$
     SELECT $2 <@ $1;
   $$ LANGUAGE SQL IMMUTABLE STRICT;

CREATE OPERATOR @> (
   LEFTARG    = spoint,
   RIGHTARG   = sbox,
   PROCEDURE  = spoint_contains_sbox,
   COMMUTATOR = '<@',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);

--------------------------------
-- the OpFamily               --
--------------------------------

CREATE OPERATOR FAMILY brin_inclusion_spheric_ops USING brin;

CREATE OR REPLACE FUNCTION spoint_brin_inclusion_add_value(internal, internal, internal, internal)
	RETURNS boolean
        AS 'MODULE_PATHNAME','spoint_brin_inclusion_add_value'
        LANGUAGE 'c';

CREATE OR REPLACE FUNCTION sbox_brin_inclusion_add_value(internal, internal, internal, internal)
	RETURNS boolean
        AS 'MODULE_PATHNAME','sbox_brin_inclusion_add_value'
        LANGUAGE 'c';

CREATE OPERATOR CLASS brin_spoint_inclusion_ops
  DEFAULT FOR TYPE spoint
  USING brin
  FAMILY brin_inclusion_spheric_ops AS
    FUNCTION      1        brin_inclusion_opcinfo(internal) ,
    FUNCTION      2        spoint_brin_inclusion_add_value(internal, internal, internal, internal) ,
    FUNCTION      3        brin_inclusion_consistent(internal, internal, internal) ,
    FUNCTION      4        brin_inclusion_union(internal, internal, internal) ,
  STORAGE spherekey;

CREATE OPERATOR CLASS brin_sbox_inclusion_ops
  DEFAULT FOR TYPE sbox
  USING brin
  FAMILY brin_inclusion_spheric_ops AS
    FUNCTION      1        brin_inclusion_opcinfo(internal) ,
    FUNCTION      2        sbox_brin_inclusion_add_value(internal, internal, internal, internal) ,
    FUNCTION      3        brin_inclusion_consistent(internal, internal, internal) ,
    FUNCTION      4        brin_inclusion_union(internal, internal, internal) ,
  STORAGE spherekey;

ALTER OPERATOR FAMILY brin_inclusion_spheric_ops USING brin ADD
    OPERATOR      3         &&(spherekey, spoint),
    OPERATOR      7         @>(spherekey, spoint),
    OPERATOR      8         <@(spherekey, spoint),

    OPERATOR      3         &&(spoint, spherekey),
    OPERATOR      7         @>(spoint, spherekey),
    OPERATOR      8         <@(spoint, spherekey),

    OPERATOR      3         &&(spherekey, sbox),
    OPERATOR      7         @>(spherekey, sbox),
    OPERATOR      8         <@(spherekey, sbox),

    OPERATOR      3         &&(sbox, spherekey),
    OPERATOR      7         @>(sbox, spherekey),
    OPERATOR      8         <@(sbox, spherekey),

    OPERATOR      3         &&(spherekey, spherekey),
    OPERATOR      7         @>(spherekey, spherekey),
    OPERATOR      8         <@(spherekey, spherekey),

    OPERATOR      3         &&(spoint, sbox),
    OPERATOR      3         &&(sbox, spoint),
    OPERATOR      7         @>(sbox, spoint),
    OPERATOR      7         @>(spoint, sbox),
    OPERATOR      8         <@(sbox, spoint),
    OPERATOR      8         <@(spoint, sbox),

    OPERATOR      3         &&(sbox, sbox),
    OPERATOR      7         @>(sbox, sbox),
    OPERATOR      8         <@(sbox, sbox);
