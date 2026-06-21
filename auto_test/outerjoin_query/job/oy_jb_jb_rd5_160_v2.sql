SELECT *
FROM title t RIGHT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN (keyword k LEFT OUTER JOIN (movie_info mi RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE mi.info_type_id % 2 = 1;
