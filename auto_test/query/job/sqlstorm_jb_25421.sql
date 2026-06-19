
SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.nr_order AS cast_order,
    rt.role AS role_type,
    mt.info AS movie_info,
    STRING_AGG(DISTINCT k.keyword, ',') AS keywords
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id 
JOIN 
    aka_title t ON c.movie_id = t.movie_id
JOIN 
    role_type rt ON c.role_id = rt.id
JOIN 
    movie_info mt ON c.movie_id = mt.movie_id AND mt.info_type_id = (SELECT id FROM info_type WHERE info = 'description')
LEFT JOIN 
    movie_keyword mk ON c.movie_id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year BETWEEN 2000 AND 2020
    AND a.name IS NOT NULL 
    AND t.title IS NOT NULL
GROUP BY 
    a.name, t.title, c.nr_order, rt.role, mt.info, t.production_year;
