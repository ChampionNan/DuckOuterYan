SELECT 
    ak.name AS aka_name,
    t.title AS movie_title,
    c.note AS cast_note,
    cn.name AS company_name,
    kt.keyword AS movie_keyword,
    pt.info AS person_info,
    rd.role AS role_type,
    CASE WHEN i.info IS NOT NULL THEN i.info ELSE 'N/A' END AS movie_info
FROM 
    aka_name ak
JOIN 
    cast_info c ON ak.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
LEFT JOIN 
    movie_info i ON t.id = i.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword kt ON mk.keyword_id = kt.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    role_type rd ON c.role_id = rd.id
LEFT JOIN 
    person_info pt ON ak.person_id = pt.person_id
WHERE 
    t.production_year > 2000
    AND cn.country_code = 'USA'
    AND ak.name IS NOT NULL;
