SELECT *
FROM title t
    RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
    LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE k.id % 7 <> 0;
