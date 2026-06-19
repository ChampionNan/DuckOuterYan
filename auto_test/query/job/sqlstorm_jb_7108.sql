
SELECT 
    t.title AS movie_title, 
    a.name AS actor_name, 
    ct.kind AS company_type, 
    mi.info AS movie_info, 
    STRING_AGG(k.keyword, ', ') AS keywords 
FROM 
    title t 
JOIN 
    movie_companies mc ON t.id = mc.movie_id 
JOIN 
    company_name cn ON mc.company_id = cn.id 
JOIN 
    company_type ct ON mc.company_type_id = ct.id 
JOIN 
    complete_cast cc ON t.id = cc.movie_id 
JOIN 
    aka_name a ON cc.subject_id = a.person_id 
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id 
WHERE 
    t.production_year BETWEEN 2000 AND 2020 
    AND ct.kind LIKE 'Production%' 
GROUP BY 
    t.title, a.name, ct.kind, mi.info;
