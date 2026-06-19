SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.note AS cast_note,
    ct.kind AS company_type,
    co.name AS company_name,
    ki.keyword AS movie_keyword,
    mi.info AS movie_info
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
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword ki ON mk.keyword_id = ki.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id
WHERE 
    t.production_year >= 2000 
    AND ct.kind = 'Distributor'
    AND a.imdb_index IS NOT NULL;
