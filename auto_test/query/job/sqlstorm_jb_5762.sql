
SELECT 
    t.title AS movie_title, 
    a.name AS actor_name, 
    c.kind AS company_type, 
    r.role AS role_name, 
    t.production_year,
    COUNT(k.keyword) AS keyword_count
FROM 
    title AS t
JOIN 
    complete_cast AS cc ON t.id = cc.movie_id
JOIN 
    cast_info AS ci ON cc.subject_id = ci.id
JOIN 
    aka_name AS a ON ci.person_id = a.person_id
JOIN 
    role_type AS r ON ci.role_id = r.id
JOIN 
    movie_companies AS mc ON t.id = mc.movie_id
JOIN 
    company_type AS c ON mc.company_type_id = c.id
LEFT JOIN 
    movie_keyword AS mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword AS k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000 
    AND c.kind = 'Distributor'
GROUP BY 
    t.title, a.name, c.kind, r.role, t.production_year;
