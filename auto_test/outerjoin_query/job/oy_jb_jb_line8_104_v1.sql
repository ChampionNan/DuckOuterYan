SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN char_name chn ON ci.person_role_id = chn.id
    FULL OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
    RIGHT OUTER JOIN kind_type kt ON t.kind_id = kt.id
WHERE ci.person_id > 100;
