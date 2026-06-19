
SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    c.nr_order AS cast_order,
    ct.kind AS cast_type,
    COALESCE(mi.info, 'No Info Available') AS movie_info,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
FROM 
    title t
JOIN 
    aka_title at ON t.id = at.movie_id
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info c ON cc.subject_id = c.person_id
JOIN 
    aka_name a ON c.person_id = a.person_id
JOIN 
    comp_cast_type ct ON c.person_role_id = ct.id
LEFT JOIN 
    movie_info mi ON t.id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Summary')
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND ct.kind IS NOT NULL
GROUP BY 
    t.title, a.name, c.nr_order, ct.kind, mi.info, t.production_year;
