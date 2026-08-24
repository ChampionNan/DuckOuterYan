SELECT *
FROM ((( title t FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id) FULL OUTER JOIN name n ON ci.person_id = n.id) FULL OUTER JOIN ( movie_keyword mk FULL OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id)
WHERE ci.person_id <= 1000;
