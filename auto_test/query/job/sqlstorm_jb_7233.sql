SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    ct.kind AS company_type,
    k.keyword AS movie_keyword,
    mpi.info AS movie_info
FROM 
    aka_title at
JOIN 
    movie_companies mc ON at.movie_id = mc.movie_id
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
JOIN 
    cast_info ci ON at.movie_id = ci.movie_id
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    title t ON at.movie_id = t.id
LEFT JOIN 
    movie_keyword mk ON at.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info mpi ON t.id = mpi.movie_id
WHERE 
    at.production_year BETWEEN 2000 AND 2023
    AND cn.country_code = 'USA'
    AND k.keyword IS NOT NULL;
