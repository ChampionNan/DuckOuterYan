SELECT *
FROM title t
    LEFT OUTER JOIN cast_info ci ON t.id = ci.movie_id
    RIGHT OUTER JOIN name n ON ci.person_id = n.id
    FULL OUTER JOIN person_info pi ON n.id = pi.person_id
WHERE t.production_year > 0 AND t.production_year < 10000;
