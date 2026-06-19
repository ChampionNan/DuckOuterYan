SELECT 
    t.title AS movie_title,
    array_agg(DISTINCT a.name) AS actors,
    co.name AS company_name,
    k.keyword AS movie_keyword,
    info.info AS additional_info
FROM 
    title t
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.person_id
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    movie_keyword mk ON t.id = mk.movie_id
JOIN 
    keyword k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id
LEFT JOIN 
    movie_info_idx info ON t.id = info.movie_id AND mi.info_type_id = info.info_type_id
WHERE 
    t.production_year > 2000 
    AND co.country_code = 'USA'
    AND ci.nr_order < 5
GROUP BY 
    t.id, co.name, k.id, info.info;
