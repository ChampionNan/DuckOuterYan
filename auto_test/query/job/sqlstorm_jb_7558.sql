SELECT 
    ak.name AS aka_name, 
    t.title AS movie_title, 
    c.nr_order AS cast_order, 
    cn.name AS company_name, 
    g.kind AS genre, 
    ti.info AS additional_info 
FROM 
    aka_name ak 
JOIN 
    cast_info c ON ak.person_id = c.person_id 
JOIN 
    aka_title t ON c.movie_id = t.movie_id 
JOIN 
    movie_companies mc ON t.id = mc.movie_id 
JOIN 
    company_name cn ON mc.company_id = cn.id 
JOIN 
    kind_type g ON t.kind_id = g.id 
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id 
LEFT JOIN 
    info_type ti ON mi.info_type_id = ti.id 
WHERE 
    t.production_year >= 2000 
    AND g.kind IN ('Drama', 'Comedy');
