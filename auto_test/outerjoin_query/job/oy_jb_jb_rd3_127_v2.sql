SELECT *
FROM title t FULL OUTER JOIN (movie_info mi RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE mk.movie_id BETWEEN 1 AND 100;
