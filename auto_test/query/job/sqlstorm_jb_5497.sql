
SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    p.info AS actor_info,
    COUNT(DISTINCT k.keyword) AS keyword_count,
    c.kind AS company_type,
    t.production_year
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.id
JOIN 
    aka_name a ON ci.person_id = a.person_id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
LEFT JOIN 
    movie_companies mc ON t.id = mc.movie_id
LEFT JOIN 
    company_type c ON mc.company_type_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year > 2000
GROUP BY 
    t.title, a.name, p.info, c.kind, t.production_year;
