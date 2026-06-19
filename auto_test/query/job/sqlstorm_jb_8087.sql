SELECT 
    t.title AS movie_title, 
    ak.name AS actor_name, 
    c.nr_order AS cast_order, 
    p.info AS person_info, 
    ki.keyword AS movie_keyword, 
    comp.name AS company_name, 
    inf.info AS movie_info
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info c ON cc.subject_id = c.person_id
JOIN 
    aka_name ak ON c.person_id = ak.person_id
LEFT JOIN 
    person_info p ON ak.person_id = p.person_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword ki ON mk.keyword_id = ki.id
LEFT JOIN 
    movie_companies mc ON t.id = mc.movie_id
LEFT JOIN 
    company_name comp ON mc.company_id = comp.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN 
    info_type inf_type ON mi.info_type_id = inf_type.id
LEFT JOIN 
    movie_info_idx inf ON t.id = inf.movie_id AND inf_type.id = inf.info_type_id
WHERE 
    t.production_year BETWEEN 2000 AND 2020 
    AND ak.name IS NOT NULL 
    AND comp.country_code = 'USA';
