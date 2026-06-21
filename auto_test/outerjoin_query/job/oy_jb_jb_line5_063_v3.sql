SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN aka_name an ON n.id = an.person_id
    FULL OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE an.person_id % 3 = 0;
