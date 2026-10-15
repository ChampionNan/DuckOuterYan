-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__job__job_21a_skeleton__left_deep__ifrl__63cc0012__sel_high__grouped_max
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT cn.id AS group_key, MAX(mc.company_id) AS max_key
FROM ((((movie_companies mc RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) INNER JOIN title t ON t.id = mc.movie_id) LEFT OUTER JOIN movie_info mi ON mi.movie_id = t.id) FULL OUTER JOIN company_name cn ON mc.company_id = cn.id)
WHERE t.production_year BETWEEN 1950 AND 2006
GROUP BY cn.id;
