SELECT *
FROM title t
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE cn.id >= 100 AND cn.id <= 9000;
