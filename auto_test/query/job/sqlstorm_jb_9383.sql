
SELECT 
    a.name AS actor_name,
    at.title AS movie_title,
    at.production_year,
    ct.kind AS company_kind,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    aka_title at ON ci.movie_id = at.id
JOIN 
    movie_companies mc ON at.id = mc.movie_id
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_keyword mk ON at.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
JOIN 
    role_type rt ON ci.role_id = rt.id
WHERE 
    at.production_year BETWEEN 2000 AND 2023
    AND ct.kind = 'Production'
GROUP BY 
    a.name, at.title, at.production_year, ct.kind;
