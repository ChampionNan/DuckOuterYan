SELECT *
FROM title t INNER JOIN (movie_info mi LEFT OUTER JOIN (info_type it FULL OUTER JOIN movie_info_idx mii ON t.id = mii.movie_id) ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE an.person_id < 50000;
