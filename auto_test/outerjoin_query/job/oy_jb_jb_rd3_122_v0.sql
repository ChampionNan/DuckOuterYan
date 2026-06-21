SELECT *
FROM title t LEFT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE ci.person_id >= 10;
