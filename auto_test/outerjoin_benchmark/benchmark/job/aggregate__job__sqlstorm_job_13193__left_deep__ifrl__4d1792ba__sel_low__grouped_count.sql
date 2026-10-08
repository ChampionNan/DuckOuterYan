-- aggregate_rewrite: aggregate-count-20261008; replaces: aggregate__job__sqlstorm_job_13193__left_deep__ifrl__4d1792ba__sel_low__grouped_sum; pending cpu9 measurement
-- corpus_revision: balanced-screened-20261002; pending cpu9 measurement
-- source: SQLStorm v1.0/job/queries/13193.sql
-- selectivity: low; base-entity cohort, not joined output
-- policy: historically screened; not an unbiased overall-performance sample
SELECT n.person_id AS group_key, COUNT(*) AS row_count
FROM ((((aka_name n INNER JOIN cast_info c ON c.person_id = n.person_id) FULL OUTER JOIN role_type r ON c.role_id = r.id) RIGHT OUTER JOIN aka_title a ON c.movie_id = a.movie_id) LEFT OUTER JOIN title m ON a.id = m.id)
WHERE m.production_year >= 2013
GROUP BY n.person_id;
