SELECT ci.role_id, COUNT(*) AS cnt_val
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
WHERE ci.person_id < 50000
GROUP BY ci.role_id;
