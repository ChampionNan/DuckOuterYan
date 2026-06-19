SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.nr_order AS actor_order,
    ct.kind AS company_type,
    mn.info AS movie_info,
    k.keyword AS movie_keyword
FROM 
    cast_info c
JOIN 
    aka_name a ON c.person_id = a.person_id
JOIN 
    aka_title t ON c.movie_id = t.movie_id
LEFT JOIN 
    movie_companies mc ON t.id = mc.movie_id
LEFT JOIN 
    company_name cn ON mc.company_id = cn.id
LEFT JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_info mn ON t.id = mn.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000 
    AND ct.kind IS NOT NULL 
    AND mn.info_type_id IN (SELECT id FROM info_type WHERE info = 'Box Office');
