SELECT *
FROM (( title t LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id) INNER JOIN (( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE mi.info_type_id < 200;
