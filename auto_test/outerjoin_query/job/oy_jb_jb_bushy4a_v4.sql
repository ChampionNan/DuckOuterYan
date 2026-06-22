SELECT *
FROM (( title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN ( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE ci.person_id % 2 = 1;
