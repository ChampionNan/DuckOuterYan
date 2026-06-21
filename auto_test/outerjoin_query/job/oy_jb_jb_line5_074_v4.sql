SELECT *
FROM title t
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    INNER JOIN keyword k ON mk.keyword_id = k.id
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mk.movie_id <= 1000;
