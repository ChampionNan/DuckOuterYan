SELECT *
FROM title t INNER JOIN (movie_keyword mk LEFT OUTER JOIN (keyword k FULL OUTER JOIN (movie_info mi RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE mc.company_id IN (2, 4, 6, 8, 10, 12, 14);
