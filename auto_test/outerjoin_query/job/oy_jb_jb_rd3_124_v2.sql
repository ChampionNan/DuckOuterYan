SELECT *
FROM title t FULL OUTER JOIN (movie_keyword mk RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE mc.company_id % 3 = 0;
