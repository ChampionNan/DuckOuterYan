-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL left-deep source-derived form
-- business_semantics: JOB 17a person-name prefix search
-- corpus_version: v2
-- selectivity_sweep: sel_medium; intended band 5–40% of the calibration population
-- semantic_filter: job_person_name; tier=medium; JOB 17a person-name prefix search
-- predicate: n.name LIKE 'B%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((((title t INNER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id)
WHERE n.name LIKE 'B%';
