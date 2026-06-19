SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    c.nr_order AS order_in_cast, 
    cn.name AS company_name, 
    mt.kind AS company_type, 
    ti.info AS movie_info 
FROM 
    aka_name a 
JOIN 
    cast_info c ON a.person_id = c.person_id 
JOIN 
    aka_title t ON c.movie_id = t.movie_id 
JOIN 
    movie_companies mc ON t.id = mc.movie_id 
JOIN 
    company_name cn ON mc.company_id = cn.id 
JOIN 
    company_type mt ON mc.company_type_id = mt.id 
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id 
LEFT JOIN 
    info_type ti ON mi.info_type_id = ti.id 
WHERE 
    a.name ILIKE '%John%' 
    AND t.production_year BETWEEN 2000 AND 2023;
