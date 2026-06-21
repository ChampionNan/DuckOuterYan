SELECT *
FROM title t FULL OUTER JOIN (cast_info ci INNER JOIN (name n LEFT OUTER JOIN (movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE t.kind_id IN (1, 5, 10, 50, 100, 500);
