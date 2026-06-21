SELECT *
FROM (( title t LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) RIGHT OUTER JOIN ( cast_info ci FULL OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE n.id > 100;
