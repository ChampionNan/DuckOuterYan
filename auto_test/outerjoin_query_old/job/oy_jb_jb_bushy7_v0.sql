SELECT *
FROM (((( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN role_type rt ON ci.role_id = rt.id) LEFT OUTER JOIN (( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE ci.role_id IN (2, 4, 6, 8, 10, 12, 14);
