SELECT *
FROM title t FULL OUTER JOIN (movie_keyword mk INNER JOIN (keyword k LEFT OUTER JOIN (movie_info mi INNER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE ci.role_id > 0 AND ci.role_id < 10000;
