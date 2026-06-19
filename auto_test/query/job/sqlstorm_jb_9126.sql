
SELECT 
    t.title AS movie_title,
    a.name AS actor_name,
    ci.role_id,
    cm.name AS company_name,
    COUNT(mk.keyword_id) AS keyword_count,
    pi.info AS person_info
FROM 
    aka_title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.id
JOIN 
    aka_name a ON ci.person_id = a.person_id
LEFT JOIN 
    movie_companies mc ON t.id = mc.movie_id
LEFT JOIN 
    company_name cm ON mc.company_id = cm.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    person_info pi ON a.person_id = pi.person_id
WHERE 
    t.production_year >= 2000
AND 
    cm.country_code = 'USA'
GROUP BY 
    t.title, a.name, ci.role_id, cm.name, pi.info;
