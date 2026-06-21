SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN role_type rt ON ci.role_id = rt.id
    LEFT OUTER JOIN char_name chn ON ci.person_role_id = chn.id
WHERE cn.id >= 10;
