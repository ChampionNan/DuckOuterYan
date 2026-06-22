SELECT ci.role_id, MIN(t.production_year) AS lo_val
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
WHERE ci.person_id <= 1000
GROUP BY ci.role_id;
