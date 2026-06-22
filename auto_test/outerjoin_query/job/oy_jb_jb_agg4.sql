SELECT cn.country_code, COUNT(*) AS cnt_val
FROM title t
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE mc.company_id IN (1, 5, 10, 50, 100, 500)
GROUP BY cn.country_code;
