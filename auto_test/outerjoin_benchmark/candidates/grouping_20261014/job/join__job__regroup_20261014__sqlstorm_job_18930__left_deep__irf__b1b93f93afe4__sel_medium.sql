-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__job__sqlstorm_job_18930__left_deep__ifr__5a608093__sel_medium
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT a.person_id, c.person_id, c.movie_id, t.movie_id, m.id
FROM (((cast_info c INNER JOIN aka_title t ON c.movie_id = t.movie_id) RIGHT OUTER JOIN title m ON t.movie_id = m.id) FULL OUTER JOIN aka_name a ON a.person_id = c.person_id)
WHERE m.production_year >= 2008;
