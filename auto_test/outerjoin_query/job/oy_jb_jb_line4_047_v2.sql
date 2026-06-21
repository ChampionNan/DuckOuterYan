SELECT *
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id
    RIGHT OUTER JOIN char_name chn ON ci.person_role_id = chn.id
WHERE an.person_id BETWEEN 50 AND 5000;
