
SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year, 
    c.kind AS cast_type, 
    STRING_AGG(DISTINCT k.keyword, ',' ORDER BY k.keyword) AS keywords 
FROM 
    aka_name a 
JOIN 
    cast_info ci ON a.person_id = ci.person_id 
JOIN 
    aka_title t ON ci.movie_id = t.movie_id 
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id 
WHERE 
    t.production_year BETWEEN 2000 AND 2023 
    AND c.kind LIKE '%actor%' 
GROUP BY 
    a.name, t.title, t.production_year, c.kind;
