
SELECT 
    t.title AS movie_title,
    ak.name AS aka_name,
    c.nr_order AS cast_order,
    r.role AS person_role,
    ci.name AS company_name,
    ci.country_code AS company_country,
    STRING_AGG(k.keyword, ', ' ORDER BY k.keyword) AS keywords
FROM 
    title t
JOIN 
    complete_cast cc ON t.id = cc.movie_id
JOIN 
    cast_info c ON cc.subject_id = c.id
JOIN 
    aka_name ak ON c.person_id = ak.person_id
JOIN 
    role_type r ON c.role_id = r.id
JOIN 
    movie_companies mc ON t.id = mc.movie_id
JOIN 
    company_name ci ON mc.company_id = ci.id
LEFT JOIN 
    movie_keyword mk ON t.id = mk.movie_id
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id
WHERE 
    t.production_year BETWEEN 2000 AND 2023
    AND ak.name IS NOT NULL
GROUP BY 
    t.title, ak.name, c.nr_order, r.role, ci.name, ci.country_code, t.production_year;
