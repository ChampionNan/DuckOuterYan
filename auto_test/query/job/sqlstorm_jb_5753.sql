SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    t.production_year,
    comp.name AS company_name,
    ct.kind AS company_type,
    COUNT(DISTINCT kc.keyword) AS keyword_count
FROM 
    cast_info ci
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    aka_title t ON ci.movie_id = t.movie_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name comp ON mc.company_id = comp.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword kc ON mk.keyword_id = kc.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND ci.nr_order = 1
GROUP BY 
    a.name, t.title, t.production_year, comp.name, ct.kind;
