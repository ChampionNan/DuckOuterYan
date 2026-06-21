SELECT *
FROM title t INNER JOIN (cast_info ci LEFT OUTER JOIN (name n FULL OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.movie_id % 7 <> 0;
