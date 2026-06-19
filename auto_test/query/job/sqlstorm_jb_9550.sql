WITH movie_data AS (
    SELECT 
        t.title,
        t.production_year,
        ak.name AS actor_name,
        c.kind AS company_type,
        k.keyword AS movie_keyword
    FROM 
        title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
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
        AND c.kind IS NOT NULL
),
ranked_movies AS (
    SELECT 
        md.*,
        ROW_NUMBER() OVER (PARTITION BY md.production_year ORDER BY md.title) AS rn
    FROM 
        movie_data md
)
SELECT 
    title, 
    production_year,
    actor_name, 
    company_type, 
    movie_keyword
FROM 
    ranked_movies
WHERE 
    rn <= 5;
