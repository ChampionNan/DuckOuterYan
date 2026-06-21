SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN aka_name an ON n.id = an.person_id
    RIGHT OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE mk.keyword_id >= 10;
