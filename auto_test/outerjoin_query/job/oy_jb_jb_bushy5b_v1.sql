SELECT *
FROM (( title t RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id) FULL OUTER JOIN (( movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE mi.movie_id BETWEEN 1 AND 100;
