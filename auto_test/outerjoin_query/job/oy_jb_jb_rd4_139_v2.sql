SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (name n LEFT OUTER JOIN aka_name an ON n.id = an.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.role_id % 3 = 0;
