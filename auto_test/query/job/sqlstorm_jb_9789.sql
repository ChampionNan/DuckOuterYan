
SELECT 
    a.name AS actor_name,
    t.title AS movie_title,
    t.production_year,
    ci.note AS role_note,
    STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
FROM 
    aka_name a
JOIN 
    cast_info ci ON a.person_id = ci.person_id
JOIN 
    title t ON ci.movie_id = t.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    a.name IS NOT NULL
    AND t.production_year > 2000
    AND ci.nr_order < 5
GROUP BY 
    a.name, t.title, t.production_year, ci.note;
