SELECT *
FROM title t FULL OUTER JOIN (complete_cast cc RIGHT OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id) ON t.id = cc.movie_id
WHERE cn.id % 2 = 1;
