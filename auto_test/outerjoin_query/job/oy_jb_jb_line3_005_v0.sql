SELECT *
FROM title t
    LEFT OUTER JOIN movie_link ml ON t.id = ml.movie_id
    RIGHT OUTER JOIN link_type lt ON ml.link_type_id = lt.id
WHERE t.kind_id IN (1, 5, 10, 50, 100, 500);
