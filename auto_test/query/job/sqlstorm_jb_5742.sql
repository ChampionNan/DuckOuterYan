WITH MovieDetails AS (
    SELECT 
        t.title, 
        t.production_year, 
        c.name AS company_name, 
        rt.role AS role_name, 
        a.name AS actor_name, 
        COUNT(DISTINCT k.keyword) AS keyword_count
    FROM 
        title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.title, t.production_year, c.name, rt.role, a.name
),
Ranking AS (
    SELECT 
        title, 
        production_year, 
        company_name, 
        role_name, 
        actor_name, 
        keyword_count,
        RANK() OVER (PARTITION BY production_year ORDER BY keyword_count DESC) AS rank
    FROM 
        MovieDetails
)
SELECT 
    title, 
    production_year, 
    company_name, 
    role_name, 
    actor_name, 
    keyword_count
FROM 
    Ranking
WHERE 
    rank <= 5;
