SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    ci.note AS role_note,
    ci.nr_order AS role_order,
    c.name AS company_name,
    ct.kind AS company_type,
    mi.info AS movie_info,
    k.keyword AS movie_keyword
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    aka_title t ON ci.movie_id = t.movie_id
JOIN 
    movie_info mi ON t.movie_id = mi.movie_id
JOIN 
    movie_companies mc ON t.movie_id = mc.movie_id
JOIN 
    company_name c ON mc.company_id = c.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_keyword mk ON t.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000
    AND ci.nr_order < 5
    AND mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'Box Office');
