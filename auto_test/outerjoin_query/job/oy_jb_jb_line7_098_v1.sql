SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE k.id BETWEEN 1 AND 100;
