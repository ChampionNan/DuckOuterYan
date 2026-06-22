SELECT *
FROM title t RIGHT OUTER JOIN (movie_link ml LEFT OUTER JOIN link_type lt ON ml.link_type_id = lt.id) ON t.id = ml.movie_id
WHERE t.production_year >= 100 AND t.production_year <= 9000;
