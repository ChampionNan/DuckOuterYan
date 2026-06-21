SELECT *
FROM title t
    RIGHT OUTER JOIN movie_link ml ON t.id = ml.movie_id
    RIGHT OUTER JOIN link_type lt ON ml.link_type_id = lt.id
WHERE k.id < 50000;
