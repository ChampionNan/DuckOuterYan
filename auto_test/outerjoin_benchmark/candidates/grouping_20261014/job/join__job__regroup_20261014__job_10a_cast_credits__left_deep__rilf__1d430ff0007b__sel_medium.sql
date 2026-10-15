-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__job__job_10a_cast_credits__left_deep__flir__b22c4687__sel_medium
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT t.id AS title_id, t.title, ci.person_id, cn.name AS company_name, rt.role, mc.company_id
FROM ((((title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN role_type rt ON rt.id = ci.role_id) LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id) FULL OUTER JOIN company_name cn ON cn.id = mc.company_id)
WHERE t.production_year >= 2008;
