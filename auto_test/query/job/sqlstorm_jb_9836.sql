SELECT 
    t.title AS movie_title,
    p.name AS actor_name,
    r.role AS actor_role,
    c.note AS casting_note,
    co.name AS company_name,
    k.keyword AS movie_keyword,
    ti.info AS additional_info,
    COUNT(*) OVER (PARTITION BY t.id) AS total_cast_count
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info c ON cc.subject_id = c.id
JOIN 
    aka_name p ON c.person_id = p.person_id
JOIN 
    role_type r ON c.role_id = r.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    movie_keyword mk ON t.id = mk.movie_id
JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN 
    info_type ti ON mi.info_type_id = ti.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND co.country_code = 'US';
