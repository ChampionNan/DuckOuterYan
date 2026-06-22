SELECT *
FROM title t RIGHT OUTER JOIN (complete_cast cc LEFT OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id) ON t.id = cc.movie_id
WHERE t.production_year > 500;
