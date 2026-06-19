SELECT 
    t.title AS movie_title,
    c.name AS cast_member_name,
    r.role AS role_name,
    p.info AS person_info,
    co.name AS company_name,
    k.keyword AS movie_keyword
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.id
JOIN 
    aka_name c ON ci.person_id = c.person_id
JOIN 
    role_type r ON ci.role_id = r.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    person_info p ON c.person_id = p.person_id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND co.country_code = 'USA';
