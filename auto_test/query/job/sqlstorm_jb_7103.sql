SELECT 
    ak.name AS actor_name,
    mv.title AS movie_title,
    ct.kind AS company_type,
    co.name AS company_name,
    ti.info AS movie_info,
    kv.keyword AS movie_keyword
FROM 
    aka_name ak
JOIN 
    cast_info ci ON ak.person_id = ci.person_id
JOIN 
    title mv ON ci.movie_id = mv.id
JOIN 
    complete_cast cc ON mv.id = cc.movie_id
JOIN 
    movie_companies mc ON mv.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
JOIN 
    movie_info mi ON mv.id = mi.movie_id
JOIN 
    info_type ti ON mi.info_type_id = ti.id
LEFT JOIN 
    movie_keyword mk ON mv.id = mk.movie_id
LEFT JOIN 
    keyword kv ON mk.keyword_id = kv.id
WHERE 
    mv.production_year BETWEEN 2000 AND 2020
    AND ak.name IS NOT NULL
    AND ti.info LIKE '%Oscar%';
