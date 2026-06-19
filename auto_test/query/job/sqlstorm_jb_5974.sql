
SELECT 
    t.title AS movie_title,
    t.production_year,
    a.name AS actor_name,
    ct.kind AS cast_type,
    STRING_AGG(k.keyword, ', ') AS keywords,
    c.name AS company_name,
    ct2.kind AS company_type
FROM 
    title t
INNER JOIN 
    cast_info ci ON t.id = ci.movie_id
INNER JOIN 
    aka_name a ON ci.person_id = a.person_id
INNER JOIN 
    comp_cast_type ct ON ci.person_role_id = ct.id
INNER JOIN 
    movie_companies mc ON t.id = mc.movie_id
INNER JOIN 
    company_name c ON mc.company_id = c.id
INNER JOIN 
    company_type ct2 ON mc.company_type_id = ct2.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000
    AND ct.kind = 'actor'
GROUP BY 
    t.title, t.production_year, a.name, ct.kind, c.name, ct2.kind;
