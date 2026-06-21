SELECT *
FROM ((( title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) RIGHT OUTER JOIN (( movie_info mi FULL OUTER JOIN info_type it ON mi.info_type_id = it.id) LEFT OUTER JOIN kind_type kt ON t.kind_id = kt.id) ON t.id = mi.movie_id)
WHERE an.person_id IN (1, 5, 10, 50, 100, 500);
