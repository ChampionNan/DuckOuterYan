SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (name n LEFT OUTER JOIN person_info pi ON n.id = pi.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE mi.movie_id BETWEEN 1 AND 100;
