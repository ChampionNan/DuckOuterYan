-- JOB 21a: retain five original tables and equality edges; vary join types.
-- Project original row identifiers to preserve observable multiplicity and NULLs.
SELECT cn.id AS company_id, ct.id AS company_type_id, mi.id AS info_id,
       mc.id AS movie_company_id, mk.id AS movie_keyword_id
FROM company_name cn LEFT JOIN
     (company_type ct RIGHT JOIN
      (movie_info mi FULL JOIN
       (movie_companies mc INNER JOIN movie_keyword mk
        ON mk.movie_id = mc.movie_id)
       ON mc.movie_id = mi.movie_id)
      ON mc.company_type_id = ct.id)
     ON mc.company_id = cn.id
WHERE cn.id % 1000 = 0;
