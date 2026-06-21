SELECT *
FROM (( title t LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) INNER JOIN ( cast_info ci RIGHT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE t.production_year % 3 = 0;
