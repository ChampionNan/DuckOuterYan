SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (name n LEFT OUTER JOIN (movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) ON t.id = mc.movie_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE mc.movie_id BETWEEN 1 AND 100;
