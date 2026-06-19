SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    c.kind AS role_type,
    cc.subject_id AS complete_cast_subject,
    m.info AS movie_info,
    COUNT(DISTINCT k.keyword) AS keyword_count
FROM 
    cast_info ci
JOIN 
    aka_name a ON ci.person_id = a.person_id
JOIN 
    aka_title t ON ci.movie_id = t.movie_id
JOIN 
    comp_cast_type c ON ci.person_role_id = c.id
JOIN 
    complete_cast cc ON ci.movie_id = cc.movie_id AND ci.person_id = cc.subject_id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year >= 2000
    AND c.kind ILIKE 'actor'
    AND m.info_type_id IN (SELECT id FROM info_type WHERE info = 'Divx')
GROUP BY 
    a.name, t.title, c.kind, cc.subject_id, m.info;
