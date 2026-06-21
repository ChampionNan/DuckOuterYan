SELECT cn.country_code, COUNT(*) AS cnt
FROM title t
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
    LEFT OUTER JOIN info_type it ON mi.info_type_id = it.id
WHERE mc.company_id % 2 = 1
GROUP BY cn.country_code;
