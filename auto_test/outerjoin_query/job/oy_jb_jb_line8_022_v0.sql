SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
    LEFT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    RIGHT OUTER JOIN company_name cn ON mc.company_id = cn.id
    FULL OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    LEFT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
WHERE mk.keyword_id % 7 <> 0;
