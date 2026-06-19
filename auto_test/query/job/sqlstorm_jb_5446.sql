
WITH movie_details AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year,
        ct.kind AS company_type,
        a.name AS actor_name,
        r.role AS role_name,
        k.keyword AS keyword
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year BETWEEN 2000 AND 2023
),
keyword_count AS (
    SELECT 
        movie_id, 
        COUNT(DISTINCT keyword) AS total_keywords 
    FROM 
        movie_details 
    GROUP BY 
        movie_id
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    md.actor_name,
    md.role_name,
    kc.total_keywords
FROM 
    movie_details md
JOIN 
    keyword_count kc ON md.movie_id = kc.movie_id;
