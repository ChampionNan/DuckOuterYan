SELECT *
FROM (( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN ( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id)
WHERE t.production_year IN (2, 4, 6, 8, 10, 12, 14);
