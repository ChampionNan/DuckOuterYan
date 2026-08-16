SELECT *
FROM title t RIGHT OUTER JOIN (movie_info mi LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id
WHERE mi.info_type_id BETWEEN 1 AND 100;
