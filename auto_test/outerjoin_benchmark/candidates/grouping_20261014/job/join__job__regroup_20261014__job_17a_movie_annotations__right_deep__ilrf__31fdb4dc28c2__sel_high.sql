-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__job__job_17a_movie_annotations__right_deep__ilfr__73c93acc__sel_high
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM (keyword k INNER JOIN (movie_keyword mk LEFT OUTER JOIN (title t RIGHT OUTER JOIN (name n FULL OUTER JOIN cast_info ci ON ci.person_id = n.id) ON t.id = ci.movie_id) ON t.id = mk.movie_id) ON mk.keyword_id = k.id)
WHERE (n.name LIKE 'A%' OR n.name LIKE 'B%' OR n.name LIKE 'C%' OR n.name LIKE 'D%' OR n.name LIKE 'E%' OR n.name LIKE 'F%' OR n.name LIKE 'G%' OR n.name LIKE 'H%' OR n.name LIKE 'I%' OR n.name LIKE 'J%' OR n.name LIKE 'K%' OR n.name LIKE 'L%');
