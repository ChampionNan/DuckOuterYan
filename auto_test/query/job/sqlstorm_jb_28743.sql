
WITH movie_data AS (
    SELECT 
        t.title AS movie_title, 
        t.production_year, 
        c.name AS company_name, 
        p.name AS person_name, 
        r.role AS person_role,
        k.keyword AS movie_keyword
    FROM 
        title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        cast_info ci ON t.id = ci.movie_id
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year >= 2000 
        AND c.country_code = 'USA'
),
keyword_count AS (
    SELECT 
        movie_title,
        COUNT(movie_keyword) AS keyword_count
    FROM 
        movie_data
    GROUP BY 
        movie_title
),
ranked_movies AS (
    SELECT 
        md.movie_title,
        md.production_year,
        md.company_name,
        md.person_name,
        md.person_role,
        kc.keyword_count,
        ROW_NUMBER() OVER (ORDER BY kc.keyword_count DESC) AS rank
    FROM 
        movie_data md
    JOIN 
        keyword_count kc ON md.movie_title = kc.movie_title
)

SELECT 
    rm.rank,
    rm.movie_title,
    rm.production_year,
    rm.company_name,
    rm.person_name,
    rm.person_role,
    rm.keyword_count
FROM 
    ranked_movies rm
WHERE 
    rm.rank <= 10;
