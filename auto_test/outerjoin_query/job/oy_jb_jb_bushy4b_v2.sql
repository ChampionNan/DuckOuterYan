SELECT *
FROM (( title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) LEFT OUTER JOIN ( cast_info ci RIGHT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE cc.movie_id BETWEEN 50 AND 5000;
