SELECT *
FROM (( title t RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) INNER JOIN ( cast_info ci FULL OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE t.id <= 1000;
