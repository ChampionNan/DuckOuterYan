SELECT *
FROM (((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) LEFT OUTER JOIN name n ON ci.person_id = n.id) RIGHT OUTER JOIN role_type rt ON ci.role_id = rt.id) FULL OUTER JOIN (( movie_companies mc LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE t.kind_id BETWEEN 1 AND 100;
