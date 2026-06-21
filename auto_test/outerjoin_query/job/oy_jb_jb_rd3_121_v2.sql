SELECT *
FROM title t FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id
WHERE ci.movie_id <= 1000;
