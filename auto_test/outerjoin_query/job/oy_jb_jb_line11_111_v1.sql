SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN aka_name an ON n.id = an.person_id
    RIGHT OUTER JOIN person_info pi ON n.id = pi.person_id
    FULL OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    LEFT OUTER JOIN company_name cn ON mc.company_id = cn.id
    RIGHT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    FULL OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT OUTER JOIN keyword k ON mk.keyword_id = k.id
    RIGHT OUTER JOIN movie_info mi ON t.id = mi.movie_id
WHERE mk.movie_id % 7 <> 0;
