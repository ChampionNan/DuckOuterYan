SELECT *
FROM title t
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    INNER JOIN company_name cn ON mc.company_id = cn.id
    RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE t.production_year > 500;
