-- candidate_revision: grouping-candidates-20261014; not active benchmark
-- source_query: aggregate__job__job_21a_skeleton__bushy__frli__ff26027f__sel_high__global_count
-- New join-type assignment; not an equivalent rewrite. Target-server verification pending.
SELECT COUNT(*) AS row_count
FROM ((movie_info mi LEFT OUTER JOIN title t ON mi.movie_id = t.id) RIGHT OUTER JOIN (company_name cn INNER JOIN (company_type ct FULL OUTER JOIN movie_companies mc ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year BETWEEN 1950 AND 2006;
