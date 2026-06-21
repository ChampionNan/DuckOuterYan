SELECT *
FROM cast_info ci
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN aka_name an ON n.id = an.person_id
WHERE t.kind_id % 3 = 0;
