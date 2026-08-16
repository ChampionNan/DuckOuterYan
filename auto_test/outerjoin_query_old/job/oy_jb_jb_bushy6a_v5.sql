SELECT *
FROM ((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) INNER JOIN name n ON ci.person_id = n.id) LEFT OUTER JOIN (( movie_companies mc INNER JOIN company_name cn ON mc.company_id = cn.id) RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE ci.person_id > 0 AND ci.person_id < 10000;
