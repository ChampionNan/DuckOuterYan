SELECT *
FROM ((( title t LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) FULL OUTER JOIN (( movie_info mi LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id) RIGHT OUTER JOIN kind_type kt ON t.kind_id = kt.id) ON t.id = mi.movie_id)
WHERE mk.keyword_id < 50000;
