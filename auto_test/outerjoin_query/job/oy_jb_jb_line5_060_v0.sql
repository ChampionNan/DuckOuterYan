SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
    LEFT OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE mi.info_type_id > 100;
