SELECT 
    a.name AS actor_name, 
    at.title AS movie_title, 
    c.nr_order AS role_order, 
    ct.kind AS company_type, 
    mc.note AS company_note,
    ti.info AS additional_info
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    aka_title at ON c.movie_id = at.movie_id
JOIN 
    movie_companies mc ON at.id = mc.movie_id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_info mi ON at.id = mi.movie_id
LEFT JOIN 
    info_type ti ON mi.info_type_id = ti.id
WHERE 
    at.production_year >= 2000 AND 
    ct.kind LIKE '%Production%';
