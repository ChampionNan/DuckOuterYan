SELECT *
FROM (((( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN role_type rt ON ci.role_id = rt.id) FULL OUTER JOIN (( movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) INNER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE ci.movie_id > 500;
