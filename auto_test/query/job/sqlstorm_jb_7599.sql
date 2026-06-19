SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.kind AS cast_type,
    p.info AS actor_info,
    m.info AS movie_info
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title t ON ci.movie_id = t.id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id AND p.info_type_id = 1
LEFT JOIN 
    movie_info m ON t.id = m.movie_id AND m.info_type_id = 2
WHERE 
    t.production_year >= 2000
    AND c.kind LIKE '%lead%';
