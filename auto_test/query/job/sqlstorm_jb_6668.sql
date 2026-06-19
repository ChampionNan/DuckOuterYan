SELECT 
    a.name AS aka_name,
    t.title AS movie_title,
    c.nr_order AS cast_order,
    p.info AS person_info,
    k.keyword AS movie_keyword,
    co.name AS company_name,
    ct.kind AS company_type,
    ti.info AS additional_info
FROM 
    aka_name AS a
JOIN 
    cast_info AS c ON a.person_id = c.person_id
JOIN 
    title AS t ON c.movie_id = t.id
LEFT JOIN 
    person_info AS p ON a.person_id = p.person_id
LEFT JOIN 
    movie_keyword AS mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword AS k ON mk.keyword_id = k.id
LEFT JOIN 
    movie_companies AS mc ON t.id = mc.movie_id
LEFT JOIN 
    company_name AS co ON mc.company_id = co.id
LEFT JOIN 
    company_type AS ct ON mc.company_type_id = ct.id
LEFT JOIN 
    movie_info AS ti ON t.id = ti.movie_id
WHERE 
    t.production_year > 2000 
    AND co.country_code IN ('USA', 'UK') 
    AND a.name IS NOT NULL;
