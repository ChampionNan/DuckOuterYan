-- query_type: graph; family: job
-- source:
-- semantic_filter: job_release_year; tier=medium; films and episodes released since a given year
-- predicate: t.production_year >= 2008
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM ((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN ( movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE t.production_year >= 2008;
