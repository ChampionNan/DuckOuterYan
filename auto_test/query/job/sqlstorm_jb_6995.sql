SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.note AS character_note,
    p.info AS person_info,
    k.keyword AS movie_keyword,
    ct.kind AS company_type,
    m.info AS movie_info
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    aka_title t ON c.movie_id = t.movie_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
JOIN 
    title ti ON ti.id = t.movie_id
JOIN 
    movie_info m ON ti.id = m.movie_id
JOIN 
    person_info p ON a.person_id = p.person_id
LEFT JOIN 
    movie_keyword mk ON ti.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year > 2000
    AND ct.kind LIKE '%Film%'
    AND p.info_type_id IN (SELECT id FROM info_type WHERE info = 'Biography');
