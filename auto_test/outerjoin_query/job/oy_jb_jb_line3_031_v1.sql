SELECT *
FROM cast_info ci
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
WHERE an.person_id >= 10;
