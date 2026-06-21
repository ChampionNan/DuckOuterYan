SELECT COUNT(*) AS total_rows, MIN(t.production_year) AS min_year, MAX(t.production_year) AS max_year
FROM title t
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE t.id IN (2, 4, 6, 8, 10, 12, 14);
