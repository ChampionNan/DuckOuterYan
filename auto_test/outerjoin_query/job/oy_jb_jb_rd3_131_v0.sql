SELECT *
FROM title t LEFT OUTER JOIN (movie_link ml RIGHT OUTER JOIN link_type lt ON ml.link_type_id = lt.id) ON t.id = ml.movie_id
WHERE n.id > 500;
