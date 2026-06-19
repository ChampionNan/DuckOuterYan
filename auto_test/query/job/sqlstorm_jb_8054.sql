
SELECT 
    t.title AS movie_title,
    ak.name AS actor_name,
    p.info AS actor_bio,
    c.kind AS company_type,
    STRING_AGG(DISTINCT k.keyword, ',' ORDER BY k.keyword) AS keywords
FROM 
    aka_title at
JOIN 
    title t ON at.movie_id = t.id
JOIN 
    cast_info ci ON t.id = ci.movie_id
JOIN 
    aka_name ak ON ci.person_id = ak.person_id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_type c ON mc.company_type_id = c.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    person_info p ON ak.person_id = p.person_id AND p.info_type_id = (SELECT id FROM info_type WHERE info = 'Biography')
WHERE 
    t.production_year > 2000
    AND c.kind LIKE '%Production%'
GROUP BY 
    t.title, ak.name, p.info, c.kind;
