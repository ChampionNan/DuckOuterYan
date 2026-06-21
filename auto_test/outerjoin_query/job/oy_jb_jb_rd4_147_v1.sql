SELECT *
FROM title t INNER JOIN (movie_companies mc LEFT OUTER JOIN (company_name cn FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id
WHERE n.id >= 100 AND n.id <= 9000;
