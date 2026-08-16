SELECT *
FROM title t FULL OUTER JOIN (cast_info ci INNER JOIN (name n LEFT OUTER JOIN person_info pi ON n.id = pi.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.role_id >= 10;
