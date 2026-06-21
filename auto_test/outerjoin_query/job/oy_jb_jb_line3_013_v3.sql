SELECT *
FROM title t
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE cc.movie_id < 50000;
