-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__job__job_10a_cast_credits__right_deep__rlif__87f83502__sel_medium__grouped_min; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 10a
-- selectivity: medium; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS group_key, COUNT(*) AS row_count
FROM (company_name cn RIGHT OUTER JOIN (movie_companies mc LEFT OUTER JOIN (role_type rt INNER JOIN (cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) ON rt.id = ci.role_id) ON t.id = mc.movie_id) ON cn.id = mc.company_id)
WHERE t.production_year BETWEEN 1995 AND 2008
GROUP BY t.id;
