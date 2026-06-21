SELECT *
FROM ((( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN ( movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE ci.role_id IN (2, 4, 6, 8, 10, 12, 14);
