SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci LEFT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.role_id <= 1000;
