
SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    r.role AS role_type,
    STRING_AGG(k.keyword, ', ') AS keywords,
    c.name AS company_name,
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
    role_type r ON ci.role_id = r.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name c ON mc.company_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id
WHERE 
    t.production_year > 2000
    AND r.role IN ('Actor', 'Actress')
GROUP BY 
    t.title, a.name, r.role, c.name, m.info, t.production_year;
