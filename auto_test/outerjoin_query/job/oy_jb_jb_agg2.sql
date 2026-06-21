SELECT ci.role_id, COUNT(*) AS cnt, AVG(t.production_year) AS avg_year
FROM title t
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    RIGHT OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE mi.movie_id > 500
GROUP BY ci.role_id;
