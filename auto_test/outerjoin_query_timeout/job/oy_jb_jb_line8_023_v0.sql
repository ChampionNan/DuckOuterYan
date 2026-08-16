SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN role_type rt ON ci.role_id = rt.id
    LEFT OUTER JOIN char_name chn ON ci.person_role_id = chn.id
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    FULL OUTER JOIN info_type it ON mi.info_type_id = it.id
    LEFT OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE ci.role_id > 0 AND ci.role_id < 10000;
