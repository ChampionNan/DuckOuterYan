SELECT *
FROM (((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN role_type rt ON ci.role_id = rt.id) INNER JOIN (( movie_companies mc RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id) FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE ci.role_id IN (1, 5, 10, 50, 100, 500);
