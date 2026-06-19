WITH movie_data AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.kind AS company_type,
        a.name AS actor_name,
        COUNT(k.keyword) AS keyword_count
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_type c ON mc.company_type_id = c.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2020
    GROUP BY 
        t.title, t.production_year, c.kind, a.name
)
SELECT 
    movie_title, 
    production_year, 
    company_type, 
    actor_name, 
    keyword_count 
FROM 
    movie_data 
WHERE 
    keyword_count > 5;
