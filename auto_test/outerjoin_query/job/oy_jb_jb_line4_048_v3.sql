SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN char_name chn ON ci.person_role_id = chn.id
WHERE t.id % 3 = 0;
