
SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year, 
    ct.kind AS company_type, 
    m.info AS movie_info, 
    COUNT(DISTINCT k.keyword) AS keyword_count
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title t ON ci.movie_id = t.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    a.name LIKE 'A%' 
    AND t.production_year >= 2000 
    AND ct.kind = 'Distributor'
GROUP BY 
    a.name, t.title, t.production_year, ct.kind, m.info;
