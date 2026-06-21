SELECT *
FROM title t
    RIGHT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE mi.movie_id % 2 = 1;
