SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.kind AS company_type,
    r.role AS actor_role,
    p.info AS personal_info,
    k.keyword AS movie_keyword
FROM 
    aka_name a
INNER JOIN 
    cast_info ci ON a.person_id = ci.person_id
INNER JOIN 
    title t ON ci.movie_id = t.id
INNER JOIN 
    movie_companies mc ON t.id = mc.movie_id
INNER JOIN 
    company_name cn ON mc.company_id = cn.id
INNER JOIN 
    company_type c ON mc.company_type_id = c.id
INNER JOIN 
    role_type r ON ci.role_id = r.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    a.name IS NOT NULL
    AND t.production_year >= 2000
    AND c.kind IN ('Distributor', 'Producer');
