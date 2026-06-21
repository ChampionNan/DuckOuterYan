SELECT *
FROM title t
    RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    INNER JOIN company_name cn ON mc.company_id = cn.id
    FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id
WHERE mc.company_id >= 100 AND mc.company_id <= 9000;
