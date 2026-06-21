SELECT *
FROM title t
    FULL OUTER JOIN complete_cast cc ON t.id = cc.movie_id
    LEFT OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id
WHERE mc.company_id BETWEEN 1 AND 100;
