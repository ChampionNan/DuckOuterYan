SELECT 
    a.name AS actor_name, 
    t.title AS movie_title, 
    t.production_year, 
    CASE 
        WHEN c.note IS NOT NULL THEN c.note 
        ELSE 'No additional info' 
    END AS role_info,
    COUNT(DISTINCT k.keyword) AS keyword_count
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
WHERE 
    t.production_year BETWEEN 2000 AND 2023
AND 
    a.name ILIKE 'John%'
GROUP BY 
    a.name, t.title, t.production_year, c.note;
