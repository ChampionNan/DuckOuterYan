SELECT *
FROM cast_info ci
    FULL OUTER JOIN name n ON ci.person_id = n.id
    LEFT OUTER JOIN aka_name an ON n.id = an.person_id
WHERE t.id BETWEEN 50 AND 5000;
