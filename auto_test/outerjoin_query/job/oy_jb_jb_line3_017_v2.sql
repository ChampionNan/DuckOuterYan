SELECT *
FROM title t
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE t.kind_id BETWEEN 50 AND 5000;
