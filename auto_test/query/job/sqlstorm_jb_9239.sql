
SELECT 
    a.name AS actor_name,
    at.title AS movie_title,
    t.production_year,
    c.kind AS cast_type,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords,
    s.info AS specific_info
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    aka_title at ON ci.movie_id = at.movie_id
JOIN 
    title t ON at.movie_id = t.id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN 
    info_type s ON mi.info_type_id = s.id
WHERE 
    t.production_year >= 2000
    AND c.kind LIKE 'Actor%'
GROUP BY 
    a.name, at.title, t.production_year, c.kind, s.info;
