SELECT *
FROM (( title t LEFT OUTER JOIN movie_info mi ON t.id = mi.movie_id) RIGHT OUTER JOIN (( movie_companies mc FULL OUTER JOIN company_name cn ON mc.company_id = cn.id) LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id) ON t.id = mc.movie_id)
WHERE mc.movie_id % 7 <> 0;
