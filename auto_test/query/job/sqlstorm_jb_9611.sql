SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.role_id,
    co.name AS company_name,
    COUNT(DISTINCT k.keyword) AS keyword_count
FROM 
    cast_info c
JOIN 
    aka_name a ON c.person_id = a.person_id
JOIN 
    aka_title t ON c.movie_id = t.movie_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000
    AND c.nr_order < 10
    AND co.country_code = 'USA'
GROUP BY 
    a.name, t.title, c.role_id, co.name;
