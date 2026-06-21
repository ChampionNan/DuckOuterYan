SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (role_type rt LEFT OUTER JOIN char_name chn ON ci.person_role_id = chn.id) ON ci.role_id = rt.id) ON t.id = ci.movie_id
WHERE mk.keyword_id % 2 = 1;
