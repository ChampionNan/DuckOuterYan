SELECT *
FROM cast_info ci LEFT OUTER JOIN (name n RIGHT OUTER JOIN aka_name an ON n.id = an.person_id) ON ci.person_id = n.id
WHERE an.person_id < 200;
