SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE mc.movie_id IN (2, 4, 6, 8, 10, 12, 14);
