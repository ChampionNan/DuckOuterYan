SELECT *
FROM title t LEFT OUTER JOIN (cast_info ci RIGHT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.person_id < 50000;
