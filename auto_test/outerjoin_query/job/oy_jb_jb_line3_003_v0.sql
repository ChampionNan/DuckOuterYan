SELECT *
FROM title t
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mi.movie_id <= 1000;
