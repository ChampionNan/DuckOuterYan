SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    r.role AS role_description,
    c.name AS company_name,
    k.keyword AS movie_keyword,
    CASE 
        WHEN ti.info IS NOT NULL THEN ti.info 
        ELSE 'No additional info' 
    END AS additional_info
FROM 
    aka_name a 
JOIN 
    cast_info ci ON a.person_id = ci.person_id 
JOIN 
    title t ON ci.movie_id = t.id 
JOIN 
    role_type r ON ci.role_id = r.id 
JOIN 
    movie_companies mc ON t.id = mc.movie_id 
JOIN 
    company_name c ON mc.company_id = c.id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id 
LEFT JOIN 
    movie_info ti ON t.id = ti.movie_id AND ti.info_type_id = (SELECT id FROM info_type WHERE info = 'Plot') 
WHERE 
    a.name LIKE 'Johnny%' AND 
    t.production_year > 2000;
