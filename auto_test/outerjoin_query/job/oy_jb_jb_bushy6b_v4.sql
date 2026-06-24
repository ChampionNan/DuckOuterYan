SELECT *
FROM (((( title t RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) INNER JOIN keyword k ON mk.keyword_id = k.id) FULL OUTER JOIN ( movie_info mi LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) RIGHT OUTER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE k.id % 2 = 1;
