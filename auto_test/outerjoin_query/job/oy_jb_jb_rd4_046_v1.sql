SELECT *
FROM title t INNER JOIN (cast_info ci LEFT OUTER JOIN (name n FULL OUTER JOIN aka_name an ON n.id = an.person_id) ON ci.person_id = n.id) ON t.id = ci.movie_id
WHERE an.person_id >= 10;
