SELECT *
FROM title t
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id
    RIGHT OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE mi.movie_id BETWEEN 50 AND 5000;
