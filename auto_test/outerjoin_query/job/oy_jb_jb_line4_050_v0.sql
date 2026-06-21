SELECT *
FROM title t
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id
    FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id
WHERE cc.movie_id IN (1, 5, 10, 50, 100, 500);
