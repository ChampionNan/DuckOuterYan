SELECT ci.role_id, MAX(t.production_year) AS hi_val
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN name n ON ci.person_id = n.id
WHERE ci.person_id BETWEEN 50 AND 5000
GROUP BY ci.role_id;
