/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

-- complain if script is sourced in psql, rather than via CREATE EXTENSION
\echo Use "CREATE EXTENSION h3" to load this file. \quit

-- ---------- ---------- ---------- ---------- ---------- ---------- ----------
--| The `h3` extension wraps the [H3 Core Library](https://github.com/uber/h3).
--| The detailed API reference is in the core [H3 Documentation](https://uber.github.io/h3) under the API Reference section.
--|
--| The `h3` core functions have been renamed from camelCase in H3 core to snake\_case in SQL.
--| The SQL function name is prefixed with `h3_`.
--|
--| # Base type
--|
--| An unsigned 64-bit integer representing any H3 object (hexagon, pentagon, directed edge ...)
--| represented as a (or 16-character) hexadecimal string, like '8928308280fffff'.
-- ---------- ---------- ---------- ---------- ---------- ---------- ----------

-- declare shell type, allowing us to reference while defining functions
-- before finally providing the full definition of the data type
CREATE TYPE h3index;

--@ internal
CREATE OR REPLACE FUNCTION
    h3index_in(cstring) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OR REPLACE FUNCTION
    h3index_out(h3index) RETURNS cstring
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OR REPLACE FUNCTION
    h3index_recv(internal) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OR REPLACE FUNCTION
    h3index_send(h3index) RETURNS bytea
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

CREATE TYPE h3index (
  INPUT          = h3index_in,
  OUTPUT         = h3index_out,
  RECEIVE        = h3index_recv,
  SEND           = h3index_send,
  LIKE           = int8
);
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Indexing functions
--|
--| These function are used for finding the H3 index containing coordinates,
--| and for finding the center and boundary of H3 indexes.

--@ availability: 4.0.0
--@ ref: h3_lat_lng_to_cell_geometry, h3_lat_lng_to_cell_geography
CREATE OR REPLACE FUNCTION
    h3_lat_lng_to_cell(latlng point, resolution integer) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_lat_lng_to_cell(point, integer)
IS 'Indexes the location at the specified resolution.';

--@ availability: 4.0.0
--@ ref: h3_cell_to_geometry, h3_cell_to_geography
CREATE OR REPLACE FUNCTION
    h3_cell_to_lat_lng(cell h3index) RETURNS point
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_lat_lng(h3index)
IS 'Finds the centroid of the index.';

--@ availability: 4.0.0
--@ ref: h3_cell_to_boundary_geometry, h3_cell_to_boundary_geography
CREATE OR REPLACE FUNCTION
    h3_cell_to_boundary(cell h3index) RETURNS polygon
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_boundary(h3index)
IS 'Finds the boundary of the index.

Use `SET h3.extend_antimeridian TO true` to extend coordinates when crossing 180th meridian.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Index inspection functions
--|
--| These functions provide metadata about an H3 index, such as its resolution
--| or base cell, and provide utilities for converting into and out of the
--| 64-bit representation of an H3 index.

--@ availability: 1.0.0
CREATE OR REPLACE FUNCTION
    h3_get_resolution(h3index) RETURNS integer
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_resolution(h3index)
IS 'Returns the resolution of the index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_base_cell_number(h3index) RETURNS integer
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_base_cell_number(h3index)
IS 'Returns the base cell number of the index.';

--@ availability: 1.0.0
CREATE OR REPLACE FUNCTION
    h3_is_valid_cell(h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_is_valid_cell(h3index)
IS 'Returns true if the given H3Index is valid.';

--@ availability: 1.0.0
CREATE OR REPLACE FUNCTION
    h3_is_res_class_iii(h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_is_res_class_iii(h3index)
IS 'Returns true if this index has a resolution with Class III orientation.';
  
--@ availability: 1.0.0
CREATE OR REPLACE FUNCTION
    h3_is_pentagon(h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_is_pentagon(h3index)
IS 'Returns true if this index represents a pentagonal cell.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_icosahedron_faces(h3index) RETURNS integer[]
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_icosahedron_faces(h3index)
IS 'Find all icosahedron faces intersected by a given H3 index.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Grid traversal functions
--|
--| Grid traversal allows finding cells in the vicinity of an origin cell, and
--| determining how to traverse the grid from one cell to another.

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_grid_disk(origin h3index, k integer DEFAULT 1) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_grid_disk(h3index, integer)
IS 'Produces indices within "k" distance of the origin index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_grid_disk_distances(origin h3index, k integer DEFAULT 1, OUT index h3index, OUT distance int) RETURNS SETOF record
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_grid_disk_distances(h3index, integer)
IS 'Produces indices within "k" distance of the origin index paired with their distance to the origin.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_grid_ring_unsafe(origin h3index, k integer DEFAULT 1) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_grid_ring_unsafe(h3index, integer)
IS 'Returns the hollow hexagonal ring centered at origin with distance "k".';

--@ availability: 4.0.0
--@ ref: h3_grid_path_cells_recursive
CREATE OR REPLACE FUNCTION
    h3_grid_path_cells(origin h3index, destination h3index) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_grid_path_cells(h3index, h3index)
IS 'Given two H3 indexes, return the line of indexes between them (inclusive).

This function may fail to find the line between two indexes, for
example if they are very far apart. It may also fail when finding
distances for indexes on opposite sides of a pentagon.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_grid_distance(origin h3index, destination h3index) RETURNS bigint
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_grid_distance(h3index, h3index)
IS 'Returns the distance in grid cells between the two indices.';    

--@ availability: 0.2.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_local_ij(origin h3index, index h3index) RETURNS point
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_local_ij(h3index, h3index)
IS 'Produces local IJ coordinates for an H3 index anchored by an origin.';

--@ availability: 0.2.0
CREATE OR REPLACE FUNCTION
    h3_local_ij_to_cell(origin h3index, coord point) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_local_ij_to_cell(h3index, point)
IS 'Produces an H3 index from local IJ coordinates anchored by an origin.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Hierarchical grid functions
--|
--| These functions permit moving between resolutions in the H3 grid system.
--| The functions produce parent (coarser) or children (finer) cells.

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_parent(cell h3index, resolution integer) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_parent(cell h3index, resolution integer)
IS 'Returns the parent of the given index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_children(cell h3index, resolution integer) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_children(cell h3index, resolution integer)
IS 'Returns the set of children of the given index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_center_child(cell h3index, resolution integer) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_center_child(cell h3index, resolution integer)
IS 'Returns the center child (finer) index contained by input index at given resolution.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_compact_cells(cells h3index[]) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_compact_cells(cells h3index[])
IS 'Compacts the given array as best as possible.';

--@ availability: 4.1.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_child_pos(child h3index, parentRes integer) RETURNS int8
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_child_pos(child h3index, parentRes integer)
IS 'Returns the position of the child cell within an ordered list of all children of the cells parent at the specified resolution parentRes. The order of the ordered list is the same as that returned by cellToChildren. This is the complement of childPosToCell.';

--@ availability: 4.1.0
CREATE OR REPLACE FUNCTION
    h3_child_pos_to_cell(childPos int8, parent h3index, childRes int) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_child_pos_to_cell(childPos int8, parent h3index, childRes int)
IS 'Returns the child cell at a given position within an ordered list of all children of parent at the specified resolution childRes. The order of the ordered list is the same as that returned by cellToChildren. This is the complement of cellToChildPos.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_uncompact_cells(cells h3index[], resolution integer) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_uncompact_cells(cells h3index[], resolution integer)
IS 'Uncompacts the given array at the given resolution.';

-- ---------- ---------- ---------- ---------- ---------- ---------- ----------
-- Custom Funtions

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_parent(cell h3index) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_parent(cell h3index)
IS 'Returns the parent of the given index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_children(cell h3index) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_children(cell h3index)
IS 'Returns the set of children of the given index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_center_child(cell h3index) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_center_child(cell h3index)
IS 'Returns the center child (finer) index contained by input index at next resolution.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_uncompact_cells(cells h3index[]) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_uncompact_cells(cells h3index[])
IS 'Uncompacts the given array at the resolution one higher than the highest resolution in the set.';


--@ internal
CREATE OR REPLACE FUNCTION __h3_cell_to_children_aux(index h3index, resolution integer, current integer) 
    RETURNS SETOF h3index AS $$
    DECLARE 
        retSet h3index[];
        r h3index;
    BEGIN
        IF current = -1 THEN 
            SELECT h3_get_resolution(index) into current;
        END IF;

        IF resolution = -1 THEN 
            SELECT h3_get_resolution(index)+1 into resolution;
        END IF;

        IF current < resolution THEN
            SELECT ARRAY(SELECT h3_cell_to_children(index)) into retSet;
            FOREACH r in ARRAY retSet LOOP
                RETURN QUERY SELECT __h3_cell_to_children_aux(r, resolution, current + 1);
            END LOOP;
        ELSE
            RETURN NEXT index;
        END IF;
    END;$$ LANGUAGE plpgsql;

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION h3_cell_to_children_slow(index h3index, resolution integer) RETURNS SETOF h3index
    AS $$ SELECT __h3_cell_to_children_aux($1, $2, -1) $$ LANGUAGE SQL;
    COMMENT ON FUNCTION h3_cell_to_children_slow(index h3index, resolution integer) IS
'Slower version of H3ToChildren but allocates less memory.';

CREATE OR REPLACE FUNCTION h3_cell_to_children_slow(index h3index) RETURNS SETOF h3index
    AS $$ SELECT __h3_cell_to_children_aux($1, -1, -1) $$ LANGUAGE SQL;
    COMMENT ON FUNCTION h3_cell_to_children_slow(index h3index) IS
'Slower version of H3ToChildren but allocates less memory.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Region functions
--|
--| These functions convert H3 indexes to and from polygonal areas.

--@ availability: 4.0.0
--@ ref: h3_polygon_to_cells_geometry, h3_polygon_to_cells_geography
CREATE OR REPLACE FUNCTION
    h3_polygon_to_cells(exterior polygon, holes polygon[], resolution integer DEFAULT 1) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE
-- intentionally NOT STRICT
CALLED ON NULL INPUT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_polygon_to_cells(polygon, polygon[], integer)
IS 'Takes an exterior polygon [and a set of hole polygon] and returns the set of hexagons that best fit the structure.';

--@ availability: 4.0.0
--@ ref: h3_cells_to_multi_polygon_geometry, h3_cells_to_multi_polygon_geography, h3_cells_to_multi_polygon_geometry_agg, h3_cells_to_multi_polygon_geography_agg
CREATE OR REPLACE FUNCTION
    h3_cells_to_multi_polygon(h3index[], OUT exterior polygon, OUT holes polygon[]) RETURNS SETOF record
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cells_to_multi_polygon(h3index[])
IS 'Create a LinkedGeoPolygon describing the outline(s) of a set of hexagons. Polygon outlines will follow GeoJSON MultiPolygon order: Each polygon will have one outer loop, which is first in the list, followed by any holes.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Unidirectional edge functions
--|
--| Unidirectional edges allow encoding the directed edge from one cell to a
--| neighboring cell.

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_are_neighbor_cells(origin h3index, destination h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_are_neighbor_cells(origin h3index, destination h3index)
IS 'Returns true if the given indices are neighbors.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cells_to_directed_edge(origin h3index, destination h3index) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cells_to_directed_edge(origin h3index, destination h3index)
IS 'Returns a unidirectional edge H3 index based on the provided origin and destination.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_is_valid_directed_edge(edge h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_is_valid_directed_edge(edge h3index)
IS 'Returns true if the given edge is valid.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_directed_edge_origin(edge h3index) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_directed_edge_origin(edge h3index)
IS 'Returns the origin index from the given edge.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_directed_edge_destination(edge h3index) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_directed_edge_destination(edge h3index)
IS 'Returns the destination index from the given edge.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_directed_edge_to_cells(edge h3index, OUT origin h3index, OUT destination h3index) RETURNS record
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_directed_edge_to_cells(edge h3index)
IS 'Returns the pair of indices from the given edge.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_origin_to_directed_edges(h3index) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_origin_to_directed_edges(h3index)
IS 'Returns all unidirectional edges with the given index as origin.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_directed_edge_to_boundary(edge h3index) RETURNS polygon
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_directed_edge_to_boundary(edge h3index)
IS 'Provides the coordinates defining the unidirectional edge.';
/*
 * Copyright 2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # H3 Vertex functions
--|
--| Functions for working with cell vertexes.

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_vertex(cell h3index, vertexNum integer) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_vertex(cell h3index, vertexNum integer)
IS 'Returns a single vertex for a given cell, as an H3 index.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_to_vertexes(cell h3index) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_vertexes(cell h3index)
IS 'Returns all vertexes for a given cell, as H3 indexes.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_vertex_to_lat_lng(vertex h3index) RETURNS point
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_vertex_to_lat_lng(vertex h3index)
IS 'Get the geocoordinates of an H3 vertex.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_is_valid_vertex(vertex h3index) RETURNS boolean
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_is_valid_vertex(vertex h3index)
IS 'Whether the input is a valid H3 vertex.';
/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Miscellaneous H3 functions
--|
--| These functions include descriptions of the H3 grid system.

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_great_circle_distance(a point, b point, unit text DEFAULT 'km') RETURNS double precision
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_great_circle_distance(point, point, text)
IS 'The great circle distance in radians between two spherical coordinates.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_hexagon_area_avg(resolution integer, unit text DEFAULT 'km') RETURNS double precision
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_hexagon_area_avg(integer, text)
IS 'Average hexagon area in square (kilo)meters at the given resolution.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_cell_area(cell h3index, unit text DEFAULT 'km^2') RETURNS double precision
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_area(h3index, text)
IS 'Exact area for a specific cell (hexagon or pentagon).';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_hexagon_edge_length_avg(resolution integer, unit text DEFAULT 'km') RETURNS double precision
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_hexagon_edge_length_avg(integer, text)
IS 'Average hexagon edge length in (kilo)meters at the given resolution.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_edge_length(edge h3index, unit text DEFAULT 'km') RETURNS double precision
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_edge_length(h3index, text)
IS 'Exact length for a specific unidirectional edge.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_num_cells(resolution integer) RETURNS bigint
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_num_cells(integer) IS
'Number of unique H3 indexes at the given resolution.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_res_0_cells() RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_res_0_cells()
IS 'Returns all 122 resolution 0 indexes.';

--@ availability: 4.0.0
CREATE OR REPLACE FUNCTION
    h3_get_pentagons(resolution integer) RETURNS SETOF h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_get_pentagons(resolution integer)
IS 'All the pentagon H3 indexes at the specified resolution.';/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Operators

--@ internal
CREATE OR REPLACE FUNCTION h3index_distance(h3index, h3index) RETURNS bigint
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 3.7.0
CREATE OPERATOR <-> (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_distance,
  COMMUTATOR = <->
);
COMMENT ON OPERATOR <-> (h3index, h3index) IS
  'Returns the distance in grid cells between the two indices (at the lowest resolution of the two).';

-- ---------- ---------- ---------- ---------- ---------- ---------- ----------
--| ## B-tree operators

--@ internal
CREATE OR REPLACE FUNCTION h3index_eq(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 0.1.0
CREATE OPERATOR = (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_eq,
  COMMUTATOR = =,
  NEGATOR = <>,
  RESTRICT = eqsel,
  JOIN = eqjoinsel,
  HASHES, MERGES
);
COMMENT ON OPERATOR = (h3index, h3index) IS
  'Returns true if two indexes are the same.';


--@ internal
CREATE OR REPLACE FUNCTION h3index_ne(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 0.1.0
CREATE OPERATOR <> (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_ne,
  COMMUTATOR = <>,
  NEGATOR = =,
  RESTRICT = neqsel,
  JOIN = neqjoinsel
);

--@ internal
CREATE OR REPLACE FUNCTION h3index_lt(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ internal
CREATE OPERATOR < (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_lt,
  COMMUTATOR = > ,
  NEGATOR = >= ,
  RESTRICT = scalarltsel,
  JOIN = scalarltjoinsel
);

--@ internal
CREATE OR REPLACE FUNCTION h3index_le(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ internal
CREATE OPERATOR <= (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_le,
  COMMUTATOR = >= ,
  NEGATOR = > ,
  RESTRICT = scalarltsel,
  JOIN = scalarltjoinsel
);

--@ internal
CREATE OR REPLACE FUNCTION h3index_gt(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ internal
CREATE OPERATOR > (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_gt,
  COMMUTATOR = < ,
  NEGATOR = <= ,
  RESTRICT = scalargtsel,
  JOIN = scalargtjoinsel
);

--@ internal
CREATE OR REPLACE FUNCTION h3index_ge(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ internal
CREATE OPERATOR >= (
  LEFTARG = h3index,
  RIGHTARG = h3index,
  PROCEDURE = h3index_ge,
  COMMUTATOR = <= ,
  NEGATOR = < ,
  RESTRICT = scalargtsel,
  JOIN = scalargtjoinsel
);

-- ---------- ---------- ---------- ---------- ---------- ---------- ----------
--| ## R-tree Operators

--@ internal
CREATE OR REPLACE FUNCTION h3index_overlaps(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 3.6.1
CREATE OPERATOR && (
	PROCEDURE = h3index_overlaps,
	LEFTARG = h3index, RIGHTARG = h3index,
	COMMUTATOR = &&,
    RESTRICT = contsel, JOIN = contjoinsel
);
COMMENT ON OPERATOR && (h3index, h3index) IS
  'Returns true if the two H3 indexes intersect.';

--@ internal
CREATE OR REPLACE FUNCTION h3index_contains(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 3.6.1
CREATE OPERATOR @> (
    PROCEDURE = h3index_contains,
    LEFTARG = h3index, RIGHTARG = h3index,
    COMMUTATOR = <@,
    RESTRICT = contsel, JOIN = contjoinsel
);
COMMENT ON OPERATOR @> (h3index, h3index) IS
  'Returns true if A contains B.';

--@ internal
CREATE OR REPLACE FUNCTION h3index_contained_by(h3index, h3index) RETURNS boolean
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
--@ availability: 3.6.1
CREATE OPERATOR <@ (
    PROCEDURE = h3index_contained_by,
    LEFTARG = h3index, RIGHTARG = h3index,
    COMMUTATOR = @>,
    RESTRICT = contsel, JOIN = contjoinsel
);
COMMENT ON OPERATOR <@ (h3index, h3index) IS
  'Returns true if A is contained by B.';
/*
 * Copyright 2019 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

-- B-tree operator class

--@ internal
CREATE OR REPLACE FUNCTION h3index_cmp(h3index, h3index) RETURNS integer
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OR REPLACE FUNCTION h3index_sortsupport(internal)
	RETURNS void
	AS 'h3', 'h3index_sortsupport'
	LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OPERATOR CLASS h3index_ops DEFAULT FOR TYPE h3index USING btree AS
    OPERATOR  1  <  ,
    OPERATOR  2  <= ,
    OPERATOR  3   = ,
    OPERATOR  4  >= ,
    OPERATOR  5  >  ,
    FUNCTION  1  h3index_cmp(h3index, h3index),
    FUNCTION  2  h3index_sortsupport(internal);
/*
 * Copyright 2019 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

-- Hash operator class

--@ internal
CREATE OR REPLACE FUNCTION h3index_hash(h3index) RETURNS integer
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OR REPLACE FUNCTION h3index_hash_extended(h3index, int8) RETURNS int8
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;

--@ internal
CREATE OPERATOR CLASS h3index_ops DEFAULT FOR TYPE h3index USING hash AS
    OPERATOR  1  = ,
    FUNCTION  1  h3index_hash(h3index),
    FUNCTION  2  h3index_hash_extended(h3index, int8);
/*
 * Copyright 2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

-- BRIN operator class

--@ internal
CREATE OPERATOR CLASS h3index_minmax_ops DEFAULT FOR TYPE h3index USING brin AS
    OPERATOR  1  <  ,
    OPERATOR  2  <= ,
    OPERATOR  3   = ,
    OPERATOR  4  >= ,
    OPERATOR  5  >  ,
    FUNCTION  1  brin_minmax_opcinfo(internal),
    FUNCTION  2  brin_minmax_add_value(internal, internal, internal, internal),
    FUNCTION  3  brin_minmax_consistent(internal, internal, internal),
    FUNCTION  4  brin_minmax_union(internal, internal, internal);
/*
 * Copyright 2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Type casts

--@ internal
CREATE OR REPLACE FUNCTION
    h3index_to_bigint(h3index) RETURNS bigint
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
CREATE CAST (h3index AS bigint) WITH FUNCTION h3index_to_bigint(h3index);
COMMENT ON CAST (h3index AS bigint) IS
    'Convert H3 index to bigint, which is useful when you need a decimal representation.';

--@ internal
CREATE OR REPLACE FUNCTION
    bigint_to_h3index(bigint) RETURNS h3index
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
CREATE CAST (bigint AS h3index) WITH FUNCTION bigint_to_h3index(bigint);
COMMENT ON CAST (h3index AS bigint) IS
    'Convert bigint to H3 index.';

CREATE CAST (h3index AS point) WITH FUNCTION h3_cell_to_lat_lng(h3index);
COMMENT ON CAST (h3index AS point) IS
    'Convert H3 index to point.';/*
 * Copyright 2018-2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Extension specific functions

--@ availability: 1.0.0
CREATE OR REPLACE FUNCTION h3_get_extension_version() RETURNS text
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
    COMMENT ON FUNCTION h3_get_extension_version() IS
'Get the currently installed version of the extension.';

--@ availability: 4.1.0
CREATE OR REPLACE FUNCTION h3_pg_migrate_pass_by_reference(h3index) RETURNS h3index
    AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE;
    COMMENT ON FUNCTION h3_pg_migrate_pass_by_reference(h3index) IS
'Migrate h3index from pass-by-reference to pass-by-value.';
/*
 * Copyright 2022 Bytes & Brains
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

--| # Deprecated functions

CREATE OR REPLACE FUNCTION
    h3_cell_to_boundary(cell h3index, extend_antimeridian boolean) RETURNS polygon
AS 'h3' LANGUAGE C IMMUTABLE STRICT PARALLEL SAFE; COMMENT ON FUNCTION
    h3_cell_to_boundary(h3index, boolean)
IS 'DEPRECATED: Use `SET h3.extend_antimeridian TO true` instead.';
