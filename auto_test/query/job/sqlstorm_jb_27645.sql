
SELECT 
    a.name AS actor_name,
    a.id AS actor_id,
    t.title AS movie_title,
    t.production_year,
    t.kind_id,
    p.info AS person_info,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords,
    c.kind AS company_type,
    m.note AS movie_note
FROM 
    aka_name a
JOIN 
    cast_info c_info ON a.person_id = c_info.person_id
JOIN 
    aka_title t ON c_info.movie_id = t.movie_id
JOIN 
    movie_companies m_comp ON t.id = m_comp.movie_id
JOIN 
    company_type c ON m_comp.company_type_id = c.id
LEFT JOIN 
    movie_info m ON t.id = m.movie_id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    a.name ILIKE '%Smith%' 
    AND t.production_year BETWEEN 2000 AND 2023 
    AND c.kind ILIKE '%Production%' 
GROUP BY 
    a.name, a.id, t.title, t.production_year, t.kind_id, p.info, c.kind, m.note;
