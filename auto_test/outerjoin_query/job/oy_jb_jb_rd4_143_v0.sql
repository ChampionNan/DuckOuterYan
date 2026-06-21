SELECT *
FROM title t FULL OUTER JOIN (cast_info ci INNER JOIN (role_type rt LEFT OUTER JOIN char_name chn ON ci.person_role_id = chn.id) ON ci.role_id = rt.id) ON t.id = ci.movie_id
WHERE mc.company_id > 0 AND mc.company_id < 10000;
