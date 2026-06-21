SELECT *
FROM title t
    LEFT OUTER JOIN movie_link ml ON t.id = ml.movie_id
    RIGHT OUTER JOIN link_type lt ON ml.link_type_id = lt.id
WHERE mi.movie_id IN (2, 4, 6, 8, 10, 12, 14);
