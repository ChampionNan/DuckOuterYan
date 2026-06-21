SELECT *
FROM title t
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mc.movie_id > 0 AND mc.movie_id < 10000;
