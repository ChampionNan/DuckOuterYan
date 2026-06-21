SELECT *
FROM title t
    FULL OUTER JOIN movie_link ml ON t.id = ml.movie_id
    LEFT OUTER JOIN link_type lt ON ml.link_type_id = lt.id
WHERE n.id < 200;
