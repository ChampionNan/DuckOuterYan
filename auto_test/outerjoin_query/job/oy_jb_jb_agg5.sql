SELECT cn.country_code, SUM(t.production_year) AS total_val
FROM title t
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE mc.company_id % 3 = 0
GROUP BY cn.country_code;
