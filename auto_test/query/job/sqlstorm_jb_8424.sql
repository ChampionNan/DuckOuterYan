SELECT 
    t.title AS movie_title, 
    a.name AS actor_name, 
    p.info AS actor_biography, 
    m.name AS production_company, 
    k.keyword AS movie_keyword, 
    i.info AS additional_info 
FROM 
    aka_title AS t 
JOIN 
    complete_cast AS cc ON t.id = cc.movie_id 
JOIN 
    cast_info AS ci ON cc.subject_id = ci.id 
JOIN 
    aka_name AS a ON ci.person_id = a.person_id 
JOIN 
    company_name AS m ON t.id = m.id 
JOIN 
    movie_keyword AS mk ON t.id = mk.movie_id 
JOIN 
    keyword AS k ON mk.keyword_id = k.id 
LEFT JOIN 
    person_info AS p ON a.person_id = p.person_id 
LEFT JOIN 
    movie_info AS i ON t.id = i.movie_id 
WHERE 
    t.production_year >= 2000 
    AND ci.nr_order < 5 
    AND m.country_code = 'USA';
