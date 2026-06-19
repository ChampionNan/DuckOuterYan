
SELECT 
    a.name AS actor_name,
    m.title AS movie_title,
    m.production_year,
    c.kind AS cast_role,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
FROM
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title m ON ci.movie_id = m.id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
LEFT JOIN 
    movie_keyword mk ON m.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    m.production_year BETWEEN 2000 AND 2020
AND 
    a.name IS NOT NULL
GROUP BY 
    a.name, m.title, m.production_year, c.kind;
