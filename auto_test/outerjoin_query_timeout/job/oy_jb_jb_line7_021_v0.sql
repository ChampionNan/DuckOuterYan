SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN role_type rt ON ci.role_id = rt.id
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE n.id % 3 = 0;
