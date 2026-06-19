SELECT 
    a.name AS aka_name,
    t.title AS movie_title,
    c.nr_order,
    r.role AS person_role,
    co.name AS company_name,
    k.keyword AS movie_keyword,
    p.info AS person_info,
    m.info AS movie_info,
    i.info AS additional_info
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
JOIN 
    role_type r ON c.role_id = r.id
JOIN 
    movie_companies mc ON c.movie_id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    movie_keyword mk ON t.id = mk.movie_id
JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    info_type i ON m.info_type_id = i.id
WHERE 
    t.production_year >= 2000
    AND co.country_code = 'USA'
    AND k.keyword ILIKE '%action%';
