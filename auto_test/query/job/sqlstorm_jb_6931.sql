
SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year, 
    r.role AS role_type, 
    c.kind AS comp_cast_kind,
    STRING_AGG(DISTINCT keyword.keyword, ',' ORDER BY keyword.keyword) AS keywords
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title t ON ci.movie_id = t.id
JOIN 
    role_type r ON ci.role_id = r.id
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    comp_cast_type c ON mc.company_type_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword ON mk.keyword_id = keyword.id
WHERE 
    a.name IS NOT NULL 
    AND t.production_year > 1990 
    AND cn.country_code = 'USA'
GROUP BY 
    a.name, t.title, t.production_year, r.role, c.kind;
