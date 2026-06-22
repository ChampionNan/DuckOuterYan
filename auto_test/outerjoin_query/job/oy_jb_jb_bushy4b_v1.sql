SELECT *
FROM (( title t RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) FULL OUTER JOIN ( cast_info ci LEFT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE ci.person_id % 2 = 1;
