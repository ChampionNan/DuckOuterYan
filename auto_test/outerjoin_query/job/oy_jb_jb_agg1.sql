SELECT ci.role_id, SUM(t.production_year) AS total_val
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
WHERE ci.person_id >= 10
GROUP BY ci.role_id;
