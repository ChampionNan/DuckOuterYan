SELECT *
FROM title t FULL OUTER JOIN (cast_info ci RIGHT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE t.production_year > 100;
