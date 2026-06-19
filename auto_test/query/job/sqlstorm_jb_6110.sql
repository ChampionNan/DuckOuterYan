SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    c.kind AS company_type, 
    m.info AS movie_info, 
    k.keyword AS movie_keyword,
    COUNT(DISTINCT ca.id) AS cast_count
FROM 
    aka_name a
JOIN 
    cast_info ca ON a.person_id = ca.person_id
JOIN 
    aka_title t ON ca.movie_id = t.movie_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_type c ON mc.company_type_id = c.id
JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND m.info_type_id IN (SELECT id FROM info_type WHERE info = 'Box Office')
GROUP BY 
    a.name, t.title, c.kind, m.info, k.keyword;
