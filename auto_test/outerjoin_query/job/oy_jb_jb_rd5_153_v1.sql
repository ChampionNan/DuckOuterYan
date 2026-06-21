SELECT *
FROM title t INNER JOIN (cast_info ci LEFT OUTER JOIN (name n FULL OUTER JOIN (aka_name an RIGHT OUTER JOIN person_info pi ON n.id = pi.person_id) ON n.id = an.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE t.production_year BETWEEN 50 AND 5000;
