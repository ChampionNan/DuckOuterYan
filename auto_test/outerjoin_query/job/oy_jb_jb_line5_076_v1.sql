SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN role_type rt ON ci.role_id = rt.id
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mi.info_type_id >= 10;
