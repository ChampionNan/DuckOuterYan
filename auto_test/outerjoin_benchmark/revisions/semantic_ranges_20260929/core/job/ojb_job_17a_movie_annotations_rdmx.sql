-- source: JOB 17a
-- transformation: connected join-subgraph adaptation; balanced INNER/LEFT/RIGHT/FULL right-deep source-derived form
-- business_semantics: JOB 17a person-name prefix search
-- corpus_revision: semantic-ranges-20260929
-- semantic_filter: job_person_name; tier=medium; JOB 17a person-name prefix search
-- predicate: n.name LIKE 'B%'
-- selectivity_scope: base-entity calibration; not a joined-output percentage
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (keyword k INNER JOIN (movie_keyword mk FULL OUTER JOIN (name n RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN title t ON t.id = ci.movie_id) ON ci.person_id = n.id) ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE n.name LIKE 'B%';
