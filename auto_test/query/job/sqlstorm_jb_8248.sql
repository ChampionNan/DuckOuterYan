SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year, 
    c.kind AS cast_category, 
    ci.note AS character_name,
    COUNT(DISTINCT kw.keyword) AS keyword_count
FROM 
    aka_name a 
JOIN 
    cast_info ci ON a.person_id = ci.person_id 
JOIN 
    title t ON ci.movie_id = t.id 
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword kw ON mk.keyword_id = kw.id 
WHERE 
    t.production_year >= 2000 
    AND a.name IS NOT NULL 
GROUP BY 
    a.name, t.title, t.production_year, c.kind, ci.note;
