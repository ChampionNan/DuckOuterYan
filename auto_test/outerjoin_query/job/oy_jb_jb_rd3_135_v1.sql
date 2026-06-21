SELECT *
FROM cast_info ci RIGHT OUTER JOIN (name n LEFT OUTER JOIN aka_name an ON n.id = an.person_id) ON ci.person_id = n.id
WHERE t.id < 50000;
