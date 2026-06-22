SELECT *
FROM ((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN ( movie_keyword mk INNER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE t.production_year > 500;
