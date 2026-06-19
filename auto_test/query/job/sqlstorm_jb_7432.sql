SELECT 
    n.name AS actor_name,
    t.title AS movie_title,
    c.nr_order AS cast_order,
    m.info AS movie_info,
    k.keyword AS movie_keyword,
    co.name AS company_name,
    ct.kind AS company_type,
    it.info AS additional_info
FROM 
    aka_name n
JOIN 
    cast_info c ON n.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    person_info pi ON n.person_id = pi.person_id
LEFT JOIN 
    info_type it ON pi.info_type_id = it.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND ct.kind = 'Production';
