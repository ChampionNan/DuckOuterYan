SELECT cn.country_code, MAX(t.production_year) AS hi_val
FROM title t
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE mc.company_id > 0 AND mc.company_id < 10000
GROUP BY cn.country_code;
