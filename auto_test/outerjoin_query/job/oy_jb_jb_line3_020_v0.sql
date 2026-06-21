SELECT *
FROM title t
    LEFT OUTER JOIN complete_cast cc ON t.id = cc.movie_id
    RIGHT OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id
WHERE ci.person_id IN (1, 5, 10, 50, 100, 500);
