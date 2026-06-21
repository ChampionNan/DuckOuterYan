SELECT *
FROM title t
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
    RIGHT OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id
WHERE mi.movie_id < 200;
