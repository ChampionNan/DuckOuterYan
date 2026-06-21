SELECT *
FROM title t
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mc.movie_id < 200;
