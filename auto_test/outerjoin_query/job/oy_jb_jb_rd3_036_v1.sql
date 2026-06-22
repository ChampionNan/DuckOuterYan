SELECT *
FROM title t RIGHT OUTER JOIN (movie_keyword mk LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id) ON t.id = mk.movie_id
WHERE t.production_year % 7 <> 0;
