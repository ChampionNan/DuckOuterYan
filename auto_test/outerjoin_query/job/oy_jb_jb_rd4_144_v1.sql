SELECT *
FROM title t INNER JOIN (cast_info ci LEFT OUTER JOIN (role_type rt FULL OUTER JOIN char_name chn ON ci.person_role_id = chn.id) ON ci.role_id = rt.id) ON t.id = ci.movie_id
WHERE mi.info_type_id IN (2, 4, 6, 8, 10, 12, 14);
