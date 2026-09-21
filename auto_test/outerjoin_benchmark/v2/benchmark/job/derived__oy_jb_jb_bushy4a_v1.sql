SELECT *
FROM (( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN ( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE mc.movie_id % 3 = 0;
