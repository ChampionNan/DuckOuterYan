SELECT *
FROM title t LEFT OUTER JOIN (complete_cast cc RIGHT OUTER JOIN comp_cast_type cct1 ON cc.subject_id = cct1.id) ON t.id = cc.movie_id
WHERE mi.info_type_id > 0 AND mi.info_type_id < 10000;
