SELECT *
FROM title t
    FULL OUTER JOIN complete_cast cc ON t.id = cc.movie_id
    FULL OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id
WHERE mk.keyword_id >= 100 AND mk.keyword_id <= 9000;
