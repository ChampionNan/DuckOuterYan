SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
    LEFT OUTER JOIN person_info pi ON n.id = pi.person_id
    RIGHT OUTER JOIN movie_companies mc ON t.id = mc.movie_id
    FULL OUTER JOIN company_name cn ON mc.company_id = cn.id
    LEFT OUTER JOIN company_type ct ON mc.company_type_id = ct.id
    RIGHT OUTER JOIN movie_keyword mk ON t.id = mk.movie_id
    FULL OUTER JOIN keyword k ON mk.keyword_id = k.id
WHERE cn.id IN (2, 4, 6, 8, 10, 12, 14);
