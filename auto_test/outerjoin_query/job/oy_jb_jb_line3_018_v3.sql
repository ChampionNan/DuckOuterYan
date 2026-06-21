SELECT *
FROM title t
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE ci.movie_id % 3 = 0;
