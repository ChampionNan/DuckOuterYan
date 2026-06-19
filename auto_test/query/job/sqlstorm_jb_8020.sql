SELECT 
    t.title AS movie_title, 
    a.name AS actor_name, 
    c.role_id AS role_id, 
    ci.kind AS comp_cast_type, 
    co.name AS company_name, 
    m.info AS movie_info, 
    k.keyword AS keyword
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info c ON cc.subject_id = c.id
JOIN 
    aka_name a ON c.person_id = a.person_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    comp_cast_type ci ON c.person_role_id = ci.id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year BETWEEN 2000 AND 2020
AND 
    a.name IS NOT NULL;
