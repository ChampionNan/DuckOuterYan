SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.kind AS cast_type,
    m.info AS movie_info,
    k.keyword AS movie_keyword,
    cp.name AS company_name,
    p.info AS person_info
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title t ON ci.movie_id = t.id
JOIN 
    kind_type c ON t.kind_id = c.id
JOIN 
    movie_info m ON t.id = m.movie_id
JOIN 
    movie_keyword mk ON t.id = mk.movie_id
JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_companies mc ON t.id = mc.movie_id
LEFT JOIN 
    company_name cp ON mc.company_id = cp.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
WHERE 
    m.info_type_id = (SELECT id FROM info_type WHERE info = 'release_date')
AND 
    k.keyword LIKE '%action%'
AND 
    t.production_year >= 2000;
