SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
WHERE ci.person_id >= 100 AND ci.person_id <= 9000;
