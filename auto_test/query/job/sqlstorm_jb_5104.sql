SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year AS release_year, 
    ci.role_id AS role_id, 
    ckm.keyword AS keyword 
FROM 
    cast_info ci 
JOIN 
    aka_name a ON ci.person_id = a.person_id 
JOIN 
    aka_title t ON ci.movie_id = t.movie_id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword ckm ON mk.keyword_id = ckm.id 
WHERE 
    t.production_year >= 2000 
AND 
    a.name ILIKE '%Smith%';
