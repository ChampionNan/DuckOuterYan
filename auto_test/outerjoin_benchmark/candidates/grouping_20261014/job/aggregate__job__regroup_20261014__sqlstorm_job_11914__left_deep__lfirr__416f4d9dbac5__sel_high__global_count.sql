-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__job__sqlstorm_job_11914__left_deep__rilfr__ad9a787a__sel_high__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM (((((cast_info ci LEFT OUTER JOIN role_type r ON ci.role_id = r.id) FULL OUTER JOIN title t ON ci.movie_id = t.id) INNER JOIN movie_companies mc ON t.id = mc.movie_id) RIGHT OUTER JOIN company_type c ON mc.company_type_id = c.id) RIGHT OUTER JOIN aka_name a ON a.person_id = ci.person_id)
WHERE t.production_year >= 2001;
