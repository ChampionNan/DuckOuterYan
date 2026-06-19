WITH movie_data AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        a.name AS actor_name,
        c.kind AS company_type,
        COUNT(DISTINCT kc.keyword) AS keyword_count
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_type c ON mc.company_type_id = c.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword kc ON mk.keyword_id = kc.id
    GROUP BY 
        t.id, a.name, t.title, t.production_year, c.kind
)
SELECT 
    movie_id,
    title,
    production_year,
    actor_name,
    company_type,
    keyword_count
FROM 
    movie_data
WHERE 
    production_year BETWEEN 2000 AND 2020;
