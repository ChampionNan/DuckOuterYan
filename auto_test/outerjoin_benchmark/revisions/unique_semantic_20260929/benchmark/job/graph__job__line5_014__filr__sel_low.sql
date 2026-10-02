-- query_type: graph; family: job
-- source:
-- semantic_filter: job_release_year; tier=low; films and episodes released since a given year
-- predicate: t.production_year >= 2013
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT *
FROM title t
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    INNER JOIN keyword k ON mk.keyword_id = k.id
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE t.production_year >= 2013;
