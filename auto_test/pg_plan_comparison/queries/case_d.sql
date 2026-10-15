-- JOB 11a: retain five original tables and equality edges; vary join types.
-- Project original row identifiers to preserve observable multiplicity and NULLs.
SELECT cn.id AS company_id, ct.id AS company_type_id, mc.id AS movie_company_id,
       mk.id AS movie_keyword_id, k.id AS keyword_id
FROM company_name cn LEFT JOIN
     (company_type ct RIGHT JOIN
      (movie_companies mc FULL JOIN
       (movie_keyword mk INNER JOIN keyword k ON mk.keyword_id = k.id)
       ON mk.movie_id = mc.movie_id)
      ON mc.company_type_id = ct.id)
     ON mc.company_id = cn.id
WHERE cn.id % 1000 = 0;
