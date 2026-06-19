
SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    c.kind AS cast_type,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords,
    m.info AS movie_info
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.id
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id AND m.info_type_id IN (SELECT id FROM info_type WHERE info IN ('Plot', 'Overview'))
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND c.kind IN ('actor', 'actress')
GROUP BY 
    t.title, a.name, c.kind, m.info;
