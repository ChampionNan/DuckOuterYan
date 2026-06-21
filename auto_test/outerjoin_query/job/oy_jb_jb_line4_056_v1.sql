SELECT *
FROM title t
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
    LEFT OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id
WHERE mc.movie_id % 2 = 1;
