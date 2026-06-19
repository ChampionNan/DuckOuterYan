SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    t.production_year,
    r.role AS role_description,
    c.kind AS company_type,
    k.keyword AS movie_keyword,
    ii.info AS additional_info
FROM 
    cast_info ci 
JOIN 
    aka_name a ON ci.person_id = a.person_id 
JOIN 
    title t ON ci.movie_id = t.id 
JOIN 
    role_type r ON ci.role_id = r.id 
JOIN 
    movie_companies mc ON t.id = mc.movie_id 
JOIN 
    company_name cn ON mc.company_id = cn.id 
JOIN 
    company_type c ON mc.company_type_id = c.id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id 
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id 
LEFT JOIN 
    info_type ii ON mi.info_type_id = ii.id 
WHERE 
    t.production_year > 2000 
    AND c.kind LIKE '%Production%' 
    AND a.name IS NOT NULL;
