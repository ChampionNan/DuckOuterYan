SELECT 
    t.title, 
    a.name AS actor_name, 
    c.kind AS cast_type, 
    m.name AS production_company, 
    COUNT(k.keyword) AS keyword_count
FROM 
    title t
JOIN 
    cast_info ci ON t.id = ci.movie_id
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name m ON mc.company_id = m.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
WHERE 
    t.production_year BETWEEN 1990 AND 2023
    AND t.kind_id IN (SELECT id FROM kind_type WHERE kind IN ('Movie', 'Series'))
GROUP BY 
    t.id, actor_name, cast_type, production_company;
