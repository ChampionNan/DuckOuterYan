SELECT 
    n.name AS person_name,
    a.title AS movie_title,
    c.nr_order AS cast_order,
    r.role AS role_type,
    m.production_year
FROM 
    cast_info c
JOIN 
    aka_name n ON c.person_id = n.person_id
JOIN 
    aka_title a ON c.movie_id = a.movie_id
JOIN 
    role_type r ON c.role_id = r.id
JOIN 
    title m ON a.id = m.id
ORDER BY 
    m.production_year DESC, c.nr_order ASC;
