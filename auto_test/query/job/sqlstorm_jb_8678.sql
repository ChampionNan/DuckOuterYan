SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    c.note AS role_note, 
    m.info AS movie_info, 
    k.keyword AS movie_keyword, 
    p.info AS person_bio 
FROM 
    aka_name a 
JOIN 
    cast_info c ON a.person_id = c.person_id 
JOIN 
    title t ON c.movie_id = t.id 
LEFT JOIN 
    movie_info m ON t.id = m.movie_id 
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id 
LEFT JOIN 
    person_info p ON a.person_id = p.person_id 
WHERE 
    t.production_year >= 2000 
    AND t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie') 
    AND m.info_type_id = (SELECT id FROM info_type WHERE info = 'Budget');
