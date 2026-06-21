SELECT t.production_year, COUNT(*) AS cnt
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
WHERE ci.person_id BETWEEN 1 AND 100
GROUP BY t.production_year;
