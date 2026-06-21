SELECT *
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN role_type rt ON ci.role_id = rt.id
    FULL OUTER JOIN char_name chn ON ci.person_role_id = chn.id
    LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    RIGHT OUTER JOIN info_type it ON mi.info_type_id = it.id
    FULL OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE ci.role_id >= 10;
