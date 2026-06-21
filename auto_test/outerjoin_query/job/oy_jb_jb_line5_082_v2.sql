SELECT *
FROM title t
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
    RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE cc.movie_id BETWEEN 1 AND 100;
