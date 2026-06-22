SELECT *
FROM ((( title t RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) LEFT OUTER JOIN (( movie_info mi RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id) FULL OUTER JOIN kind_type kt ON t.kind_id = kt.id) ON t.id = mi.movie_id)
WHERE t.production_year % 3 = 0;
