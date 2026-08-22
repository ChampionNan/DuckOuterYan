SELECT *
FROM (( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN ( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE cn.id > 0 AND cn.id < 10000;
