SELECT *
FROM title t RIGHT OUTER JOIN (movie_info mi RIGHT OUTER JOIN (info_type it LEFT OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id) ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE t.id <= 1000;
