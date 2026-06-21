SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE ci.person_id > 500;
