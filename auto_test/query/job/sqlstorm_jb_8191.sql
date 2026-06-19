SELECT 
    t.title AS movie_title,
    n.name AS actor_name,
    c.kind AS cast_type,
    p.info AS person_info,
    k.keyword AS movie_keyword,
    cmp.name AS company_name,
    ci.note AS cast_note
FROM 
    title t
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name cmp ON mc.company_id = cmp.id
JOIN 
    cast_info ci ON t.id = ci.movie_id
JOIN 
    aka_name n ON ci.person_id = n.person_id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
LEFT JOIN 
    person_info p ON n.person_id = p.person_id AND p.info_type_id = (SELECT id FROM info_type WHERE info = 'Birth Date')
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000 AND
    cmp.country_code = 'USA' AND
    k.keyword ILIKE '%action%';
