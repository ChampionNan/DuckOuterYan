SELECT *
FROM title t
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
    FULL OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id
WHERE t.production_year > 500;
