SELECT *
FROM title t FULL OUTER JOIN (movie_companies mc INNER JOIN (company_name cn LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id
WHERE mk.movie_id > 500;
