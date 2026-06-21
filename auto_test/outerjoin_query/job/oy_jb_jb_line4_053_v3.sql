SELECT *
FROM title t
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    INNER JOIN company_name cn ON mc.company_id = cn.id
    RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
WHERE ci.role_id > 500;
