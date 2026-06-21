SELECT *
FROM (( title t RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN ( movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE mk.movie_id >= 100 AND mk.movie_id <= 9000;
