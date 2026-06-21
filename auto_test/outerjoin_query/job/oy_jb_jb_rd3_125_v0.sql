SELECT *
FROM title t LEFT OUTER JOIN (movie_info mi RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE mc.movie_id IN (1, 5, 10, 50, 100, 500);
