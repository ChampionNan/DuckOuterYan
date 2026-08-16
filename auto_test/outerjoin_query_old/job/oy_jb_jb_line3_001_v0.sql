SELECT *
FROM title t
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE t.production_year < 50000;
