SELECT *
FROM title t
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE k.id < 200;
