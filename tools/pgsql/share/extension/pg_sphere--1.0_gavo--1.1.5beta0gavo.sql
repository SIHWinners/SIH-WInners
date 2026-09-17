-- complain if this upgrade script is run via psql
\echo Use "ALTER EXTENSION pg_sphere UPDATE TO '1.1.5beta0gavo'" to load this file. \quit
-- create the next generation operator class for spherical points

CREATE FUNCTION g_spoint3_union(bytea, internal)
	RETURNS spherekey
	AS 'MODULE_PATHNAME', 'g_spoint3_union'
	LANGUAGE 'c';	

CREATE FUNCTION g_spoint3_penalty (internal, internal, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_penalty'
	LANGUAGE 'c'
	STRICT PARALLEL SAFE;

CREATE FUNCTION g_spoint3_picksplit(internal, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_picksplit'
	LANGUAGE 'c';

CREATE FUNCTION g_spoint3_same (bytea, bytea, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_same'
	LANGUAGE 'c';

CREATE FUNCTION g_spoint3_compress(internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_compress'
	LANGUAGE 'c';	

CREATE FUNCTION g_spoint3_consistent(internal, internal, int4, oid, internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_consistent'
	LANGUAGE 'c';	

CREATE FUNCTION g_spoint3_distance(internal, internal, int4, oid)
	RETURNS float8
	AS 'MODULE_PATHNAME', 'g_spoint3_distance'
	LANGUAGE 'c';	

CREATE FUNCTION g_spoint3_fetch(internal)
	RETURNS internal
	AS 'MODULE_PATHNAME', 'g_spoint3_fetch'
	LANGUAGE 'c'
	STRICT PARALLEL SAFE;

CREATE OPERATOR CLASS spoint3
	FOR TYPE spoint USING gist AS
	OPERATOR   1 = (spoint, spoint),
	OPERATOR  11 @ (spoint, scircle),
	OPERATOR  12 @ (spoint, sline),
	OPERATOR  13 @ (spoint, spath),
	OPERATOR  14 @ (spoint, spoly),
	OPERATOR  15 @ (spoint, sellipse),
	OPERATOR  16 @ (spoint, sbox),
	OPERATOR  37 <@ (spoint, scircle),
	OPERATOR  38 <@ (spoint, sline),
	OPERATOR  39 <@ (spoint, spath),
	OPERATOR  40 <@ (spoint, spoly),
	OPERATOR  41 <@ (spoint, sellipse),
	OPERATOR  42 <@ (spoint, sbox),
	OPERATOR  100 <-> (spoint, spoint) FOR ORDER BY float_ops,
	FUNCTION  1 g_spoint3_consistent (internal, internal, int4, oid, internal),
	FUNCTION  2 g_spoint3_union (bytea, internal),
	FUNCTION  3 g_spoint3_compress (internal),
	FUNCTION  4 g_spherekey_decompress (internal),
	FUNCTION  5 g_spoint3_penalty (internal, internal, internal),
	FUNCTION  6 g_spoint3_picksplit (internal, internal),
	FUNCTION  7 g_spoint3_same (bytea, bytea, internal),
	FUNCTION  8 g_spoint3_distance (internal, internal, int4, oid),
	FUNCTION  9 (spoint, spoint) g_spoint3_fetch (internal),
	STORAGE	pointkey;
-- fix typo in commutator of OPERATOR !@>(spoly, sellipse) (a.k.a. !~) introduced in commits 2798ed96f9282ddeee21d5ddd3e256bbb9b4f36f and 244c1549c492426b62bc926c9ac2ad21f3ccd0c1

DROP OPERATOR !@> (spoly, sellipse) CASCADE;
DROP OPERATOR  !~ (spoly, sellipse) CASCADE;

CREATE OPERATOR !@> (
   LEFTARG    = spoly,
   RIGHTARG   = sellipse,
   PROCEDURE  = spoly_contains_ellipse_neg,
   COMMUTATOR = '!<@',
   NEGATOR    = '@>',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);
COMMENT ON OPERATOR !@> (spoly, sellipse) IS 'true if spherical polygon (LHS) does not contain spherical ellipse (RHS)';

CREATE OPERATOR !~ (
   LEFTARG    = spoly,
   RIGHTARG   = sellipse,
   PROCEDURE  = spoly_contains_ellipse_neg,
   COMMUTATOR = '!@',
   NEGATOR    = '~',
   RESTRICT   = contsel,
   JOIN       = contjoinsel
);
COMMENT ON OPERATOR !~ (spoly, sellipse) IS 'true if spherical polygon (LHS) does not contain spherical ellipse (RHS)';
DROP OPERATOR CLASS IF EXISTS spoint2 USING gist CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_union(bytea, internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_penalty (internal, internal, internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_picksplit(internal, internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_same (bytea, bytea, internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_compress(internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_consistent(internal, internal, int4, oid, internal) CASCADE;
DROP FUNCTION IF EXISTS g_spoint2_distance(internal, internal, int4, oid) CASCADE;

DROP FUNCTION IF EXISTS crossmatch(text, text, float8);
DROP FUNCTION IF EXISTS crossmatch(text, text, float8, sbox);
