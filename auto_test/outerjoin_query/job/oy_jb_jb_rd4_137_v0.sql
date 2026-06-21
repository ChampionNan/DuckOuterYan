SELECT *
FROM title t FULL OUTER JOIN (cast_info ci INNER JOIN (name n LEFT OUTER JOIN aka_name an ON n.id = an.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE t.production_year >= 10;
