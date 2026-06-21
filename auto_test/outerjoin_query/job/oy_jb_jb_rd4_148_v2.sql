SELECT *
FROM title t RIGHT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN (company_name cn LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON mc.company_id = cn.id) ON t.id = mc.movie_id
WHERE k.id > 100;
