SELECT 
    p.name AS actor_name, 
    m.title AS movie_title, 
    m.production_year,
    c.kind AS company_type,
    COUNT(DISTINCT kw.keyword) AS keyword_count
FROM 
    cast_info ci
JOIN 
    aka_name p ON ci.person_id = p.person_id
JOIN 
    aka_title m ON ci.movie_id = m.movie_id
JOIN 
    movie_companies mc ON m.id = mc.movie_id
JOIN 
    company_type c ON mc.company_type_id = c.id
LEFT JOIN 
    movie_keyword mk ON m.id = mk.movie_id
LEFT JOIN 
    keyword kw ON mk.keyword_id = kw.id
WHERE 
    m.production_year BETWEEN 2000 AND 2023
    AND c.kind LIKE 'Production%'
GROUP BY 
    p.name, m.title, m.production_year, c.kind;
