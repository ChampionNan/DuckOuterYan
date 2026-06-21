SELECT *
FROM title t
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
    LEFT OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE mk.movie_id IN (1, 5, 10, 50, 100, 500);
