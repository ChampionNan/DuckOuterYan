WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS rn,
        COUNT(*) OVER (PARTITION BY a.production_year) AS total_movies
    FROM 
        aka_title a
),
ActorMovies AS (
    SELECT 
        ca.person_id,
        ca.movie_id,
        p.name,
        a.title AS movie_title,
        a.production_year
    FROM 
        cast_info ca
    JOIN 
        aka_name p ON ca.person_id = p.person_id
    JOIN 
        aka_title a ON ca.movie_id = a.movie_id
    WHERE 
        p.name IS NOT NULL
),
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    am.name AS actor_name,
    cm.company_name,
    cm.company_type,
    'Rank: ' || rm.rn || ' of ' || rm.total_movies AS ranking_info
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorMovies am ON rm.movie_id = am.movie_id
LEFT JOIN 
    CompanyMovies cm ON rm.movie_id = cm.movie_id
WHERE 
    rm.production_year >= 2000 
    AND (cm.company_type IS NULL OR cm.company_type <> 'Distributor');
