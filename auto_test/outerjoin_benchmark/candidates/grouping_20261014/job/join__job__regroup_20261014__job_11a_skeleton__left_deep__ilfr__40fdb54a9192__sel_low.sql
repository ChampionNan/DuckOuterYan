-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: join__job__job_11a_skeleton__left_deep__lrif__dcc3f549__sel_low
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT mc.company_id, cn.id, t.id, mc.movie_id, mc.company_type_id, ct.id, mk.movie_id
FROM ((((company_name cn INNER JOIN movie_companies mc ON mc.company_id = cn.id) LEFT OUTER JOIN title t ON t.id = mc.movie_id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id)
WHERE t.production_year BETWEEN 1999 AND 2000;
