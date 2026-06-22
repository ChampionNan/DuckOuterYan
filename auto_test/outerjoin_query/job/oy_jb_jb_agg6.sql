SELECT cn.country_code, MIN(t.production_year) AS lo_val
FROM title t
    RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE mc.company_id % 7 <> 0
GROUP BY cn.country_code;
