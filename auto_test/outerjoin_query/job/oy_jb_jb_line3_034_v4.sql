SELECT *
FROM cast_info ci
    FULL OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN aka_name an ON n.id = an.person_id
WHERE ci.movie_id > 0 AND ci.movie_id < 10000;
