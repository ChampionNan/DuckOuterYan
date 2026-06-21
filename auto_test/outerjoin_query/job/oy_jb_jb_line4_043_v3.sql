SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    INNER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE n.id < 50000;
