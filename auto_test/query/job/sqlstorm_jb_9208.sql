SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.role_id,
    c.nr_order,
    co.name AS company_name,
    ti.info AS movie_info,
    k.keyword AS movie_keyword
FROM 
    cast_info c
JOIN 
    aka_name a ON c.person_id = a.person_id
JOIN 
    complete_cast cc ON cc.subject_id = a.id
JOIN 
    title t ON cc.movie_id = t.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    movie_info mi ON t.id = mi.movie_id
JOIN 
    info_type ti ON mi.info_type_id = ti.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year > 2000
    AND co.country_code = 'USA';
