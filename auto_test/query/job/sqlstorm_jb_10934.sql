SELECT 
    t.title AS movie_title,
    ak.name AS person_name,
    ct.kind AS company_type,
    p.info AS person_info,
    k.keyword AS movie_keyword
FROM 
    title t
JOIN 
    aka_title ak_t ON ak_t.movie_id = t.id
JOIN 
    aka_name ak ON ak.person_id = ak_t.id
JOIN 
    cast_info ci ON ci.movie_id = t.id 
JOIN 
    company_name cn ON cn.imdb_id = ci.person_id
JOIN 
    movie_companies mc ON mc.movie_id = t.id AND mc.company_id = cn.id
JOIN 
    company_type ct ON ct.id = mc.company_type_id
JOIN 
    person_info p ON p.person_id = ak.person_id
LEFT JOIN 
    movie_keyword mk ON mk.movie_id = t.id
LEFT JOIN 
    keyword k ON k.id = mk.keyword_id
WHERE 
    t.production_year >= 2000;
