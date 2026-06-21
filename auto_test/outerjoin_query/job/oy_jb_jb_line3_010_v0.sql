SELECT *
FROM title t
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mk.movie_id IN (2, 4, 6, 8, 10, 12, 14);
