
SELECT 
    a.id AS aka_id,
    a.person_id AS aka_person_id,
    a.name AS aka_name,
    t.id AS title_id,
    t.title AS movie_title,
    t.production_year,
    c.role_id,
    p.info AS person_info,
    STRING_AGG(DISTINCT k.keyword, ',') AS keywords,
    co.name AS company_name,
    ct.kind AS company_type,
    yt.title AS episode_title
FROM 
    aka_name a
JOIN 
    cast_info c ON a.person_id = c.person_id
JOIN 
    title t ON c.movie_id = t.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name co ON mc.company_id = co.id
JOIN 
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN 
    title yt ON t.episode_of_id = yt.id
LEFT JOIN 
    person_info p ON a.person_id = p.person_id AND p.info_type_id = (SELECT id FROM info_type WHERE info = 'Biography')
WHERE 
    a.name ILIKE '%Smith%' 
    AND t.production_year >= 2000
GROUP BY 
    a.id, a.person_id, a.name, t.id, t.title, t.production_year, c.role_id, p.info, co.name, ct.kind, yt.title;
