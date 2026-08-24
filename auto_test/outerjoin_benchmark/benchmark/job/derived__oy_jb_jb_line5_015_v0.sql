SELECT *
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN role_type rt ON ci.role_id = rt.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mk.movie_id > 100;
