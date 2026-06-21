SELECT *
FROM ((( title t LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id) RIGHT OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN ( movie_keyword mk LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE cc.movie_id BETWEEN 50 AND 5000;
