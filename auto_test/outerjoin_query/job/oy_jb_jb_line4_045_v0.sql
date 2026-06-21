SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN role_type rt ON ci.role_id = rt.id
    FULL OUTER JOIN char_name chn ON ci.person_role_id = chn.id
WHERE mk.keyword_id > 100;
