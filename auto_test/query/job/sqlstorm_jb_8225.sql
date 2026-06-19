SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    co.name AS company_name,
    k.keyword AS movie_keyword,
    p.info AS actor_info
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
WHERE 
    t.production_year >= 2000 
    AND co.country_code = 'USA'
    AND p.info_type_id IN (SELECT id FROM info_type WHERE info = 'Biography');
