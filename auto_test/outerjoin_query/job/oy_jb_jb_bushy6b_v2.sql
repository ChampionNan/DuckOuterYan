SELECT *
FROM (((( title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) RIGHT OUTER JOIN ( movie_info mi FULL OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) LEFT OUTER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE mi.movie_id > 0 AND mi.movie_id < 10000;
