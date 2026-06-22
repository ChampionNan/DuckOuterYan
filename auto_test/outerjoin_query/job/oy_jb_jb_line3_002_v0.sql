SELECT *
FROM title t
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE t.kind_id >= 10;
