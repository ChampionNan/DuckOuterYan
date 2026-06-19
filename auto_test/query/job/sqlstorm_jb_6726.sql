WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.kind AS company_type,
        a.name AS actor_name,
        r.role AS role_name,
        COUNT(DISTINCT kw.keyword) AS keyword_count
    FROM 
        title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON ci.movie_id = cc.movie_id AND ci.id = cc.subject_id
    JOIN 
        aka_name a ON a.person_id = ci.person_id
    JOIN 
        movie_companies mc ON mc.movie_id = t.id
    JOIN 
        company_type c ON c.id = mc.company_type_id
    JOIN 
        role_type r ON r.id = ci.role_id
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = t.id
    LEFT JOIN 
        keyword kw ON kw.id = mk.keyword_id
    WHERE 
        t.production_year >= 2000
        AND t.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
    GROUP BY 
        t.id, t.title, t.production_year, c.kind, a.name, r.role
),
RankedMovies AS (
    SELECT 
        md.*, 
        RANK() OVER (PARTITION BY md.production_year ORDER BY md.keyword_count DESC) AS rank
    FROM 
        MovieDetails md
)
SELECT 
    movie_title, 
    production_year, 
    company_type, 
    actor_name, 
    role_name, 
    keyword_count
FROM 
    RankedMovies
WHERE 
    rank <= 5;
