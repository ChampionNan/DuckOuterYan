SELECT *
FROM (( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN ( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE ci.movie_id BETWEEN 50 AND 5000;
