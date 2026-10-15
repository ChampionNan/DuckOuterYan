-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__job__job_17a_movie_annotations__bushy__rfli__b51402ae__sel_medium
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT t.id AS title_id, t.title, n.id AS person_id, n.name, mk.keyword_id, k.keyword
FROM ((name n FULL OUTER JOIN cast_info ci ON ci.person_id = n.id) INNER JOIN (title t RIGHT OUTER JOIN (keyword k LEFT OUTER JOIN movie_keyword mk ON mk.keyword_id = k.id) ON t.id = mk.movie_id) ON t.id = ci.movie_id)
WHERE n.name LIKE 'B%';
