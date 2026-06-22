SELECT *
FROM (( title t FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id) INNER JOIN ( cast_info ci LEFT OUTER JOIN name n ON ci.person_id = n.id) ON t.id = ci.movie_id)
WHERE t.kind_id IN (1, 5, 10, 50, 100, 500);
