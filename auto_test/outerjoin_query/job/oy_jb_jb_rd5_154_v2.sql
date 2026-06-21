SELECT *
FROM title t RIGHT OUTER JOIN (cast_info ci RIGHT OUTER JOIN (name n LEFT OUTER JOIN (aka_name an RIGHT OUTER JOIN person_info pi ON n.id = pi.person_id) ON n.id = an.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE ci.person_id % 3 = 0;
