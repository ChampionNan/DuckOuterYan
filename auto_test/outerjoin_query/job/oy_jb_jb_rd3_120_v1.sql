SELECT *
FROM title t RIGHT OUTER JOIN (movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id
WHERE t.kind_id < 50000;
