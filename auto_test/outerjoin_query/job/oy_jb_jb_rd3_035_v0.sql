SELECT *
FROM title t LEFT OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE k.id IN (1, 5, 10, 50, 100, 500);
