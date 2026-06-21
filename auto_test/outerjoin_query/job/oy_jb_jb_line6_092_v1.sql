SELECT *
FROM title t
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
    FULL OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE mi.movie_id <= 1000;
