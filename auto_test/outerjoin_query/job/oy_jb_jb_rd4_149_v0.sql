SELECT *
FROM title t FULL OUTER JOIN (movie_info mi INNER JOIN (info_type it LEFT OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id) ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE cn.id < 200;
