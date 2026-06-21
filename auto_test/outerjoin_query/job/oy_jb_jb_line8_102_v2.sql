SELECT *
FROM title t
    FULL OUTER JOIN cast_info ci ON t.id = ci.movie_id
    LEFT OUTER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN aka_name an ON n.id = an.person_id
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
    RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE t.kind_id < 200;
