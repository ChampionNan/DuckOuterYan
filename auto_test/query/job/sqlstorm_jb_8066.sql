
SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    ct.kind AS company_type, 
    k.keyword AS movie_keyword, 
    pi.info AS person_info
FROM 
    aka_name AS a 
JOIN 
    cast_info AS ci ON a.person_id = ci.person_id 
JOIN 
    title AS t ON ci.movie_id = t.id 
JOIN 
    movie_companies AS mc ON t.id = mc.movie_id 
JOIN 
    company_name AS cn ON mc.company_id = cn.id 
JOIN 
    company_type AS ct ON mc.company_type_id = ct.id 
LEFT JOIN 
    movie_keyword AS mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword AS k ON mk.keyword_id = k.id 
LEFT JOIN 
    person_info AS pi ON a.person_id = pi.person_id 
WHERE 
    t.production_year >= 2000 
    AND ct.kind = 'Distributor' 
    AND pi.info_type_id = (SELECT id FROM info_type WHERE info = 'Birthdate') 
GROUP BY 
    a.name, t.title, ct.kind, k.keyword, pi.info;
