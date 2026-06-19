
SELECT 
    a.name AS actor_name,
    m.title AS movie_title,
    m.production_year,
    c.role_id,
    ct.kind AS company_type,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    aka_title m ON c.movie_id = m.movie_id
JOIN 
    movie_companies mc ON m.id = mc.movie_id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_keyword mk ON m.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    m.production_year BETWEEN 2000 AND 2020
    AND ct.kind IN ('Distributor', 'Production')
GROUP BY 
    a.name, m.title, m.production_year, c.role_id, ct.kind;
