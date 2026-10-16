-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__job__job_20a_skeleton__bushy__flri__f60cc233__sel_low__grouped_min; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: JOB 20a
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT t.id AS group_key, COUNT(*) AS row_count
FROM ((cast_info ci FULL OUTER JOIN title t ON t.id = ci.movie_id) LEFT OUTER JOIN (comp_cast_type cct2 RIGHT OUTER JOIN (complete_cast cc INNER JOIN comp_cast_type cct1 ON cct1.id = cc.subject_id) ON cct2.id = cc.status_id) ON t.id = cc.movie_id)
WHERE t.production_year >= 2013
GROUP BY t.id;
