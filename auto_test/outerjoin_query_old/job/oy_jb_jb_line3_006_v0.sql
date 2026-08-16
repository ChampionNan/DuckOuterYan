SELECT *
FROM cast_info ci
    LEFT OUTER JOIN name n ON ci.person_id = n.id
    RIGHT OUTER JOIN aka_name an ON n.id = an.person_id
WHERE ci.movie_id % 3 = 0;
