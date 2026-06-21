SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN role_type rt ON ci.role_id = rt.id
    FULL OUTER JOIN char_name chn ON ci.person_role_id = chn.id
WHERE t.kind_id > 0 AND t.kind_id < 10000;
