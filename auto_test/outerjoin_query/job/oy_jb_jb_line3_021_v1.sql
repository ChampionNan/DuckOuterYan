SELECT *
FROM title t
    RIGHT OUTER JOIN complete_cast cc ON t.id = cc.movie_id
    FULL OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id
WHERE ci.role_id % 7 <> 0;
