SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.note AS role_note,
    m.production_year AS year_produced
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    aka_title t ON c.movie_id = t.movie_id
JOIN 
    title m ON t.movie_id = m.id
WHERE 
    m.production_year > 2000
ORDER BY 
    m.production_year DESC;
