SELECT *
FROM (((( title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) FULL OUTER JOIN ( movie_info mi FULL OUTER JOIN info_type it ON mi.info_type_id = it.id) ON t.id = mi.movie_id) FULL OUTER JOIN kind_type kt ON t.kind_id = kt.id)
WHERE k.id BETWEEN 50 AND 5000;
