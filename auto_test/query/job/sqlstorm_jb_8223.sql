WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword LIKE '%action%'
),
TopActors AS (
    SELECT 
        a.name,
        ci.movie_id,
        COUNT(ci.person_id) AS role_count
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        RankedMovies rm ON ci.movie_id = rm.movie_id
    GROUP BY 
        a.name, ci.movie_id
    ORDER BY 
        role_count DESC
),
MoviesWithCompanies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        RankedMovies rm
    JOIN 
        movie_companies mc ON rm.movie_id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    r.title AS movie_title,
    r.production_year,
    a.name AS actor_name,
    a.role_count,
    c.company_name,
    c.company_type
FROM 
    RankedMovies r
LEFT JOIN 
    TopActors a ON r.movie_id = a.movie_id
LEFT JOIN 
    MoviesWithCompanies c ON r.movie_id = c.movie_id
WHERE 
    r.year_rank <= 5;
