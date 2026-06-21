SELECT *
FROM title t
    FULL OUTER JOIN movie_link ml ON t.id = ml.movie_id
    FULL OUTER JOIN link_type lt ON ml.link_type_id = lt.id
WHERE cc.movie_id <= 1000;
