SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    co.name AS company_name, 
    rt.role AS role_type, 
    COUNT(DISTINCT kc.keyword) AS keyword_count
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    role_type rt ON c.role_id = rt.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword kc ON mk.keyword_id = kc.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023 
    AND co.country_code = 'USA'
    AND rt.role IN ('Actor', 'Director')
GROUP BY 
    a.name, t.title, co.name, rt.role;
