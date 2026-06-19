
SELECT 
    p.name AS person_name,
    m.title AS movie_title,
    c.role_id,
    r.role AS role_name,
    c.nr_order,
    ci.kind AS comp_cast_type_name,
    co.name AS company_name,
    k.keyword AS movie_keyword,
    mi.info AS movie_info,
    m.production_year
FROM 
    name p
JOIN 
    cast_info c ON p.id = c.person_id
JOIN 
    title m ON c.movie_id = m.id
LEFT JOIN 
    role_type r ON c.role_id = r.id
JOIN 
    complete_cast cc ON m.id = cc.movie_id
JOIN 
    movie_companies mc ON m.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    comp_cast_type ci ON c.person_role_id = ci.id
LEFT JOIN 
    movie_keyword mk ON m.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info mi ON m.id = mi.movie_id
WHERE 
    m.production_year >= 2000
AND 
    p.gender = 'F'
GROUP BY 
    p.name, 
    m.title, 
    c.role_id, 
    r.role, 
    c.nr_order, 
    ci.kind, 
    co.name, 
    k.keyword, 
    mi.info, 
    m.production_year;
