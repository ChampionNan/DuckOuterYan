WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.kind_id ORDER BY t.production_year DESC) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
Actors AS (
    SELECT 
        ca.movie_id,
        a.name,
        COUNT(*) AS role_count
    FROM 
        cast_info ca
    JOIN 
        aka_name a ON ca.person_id = a.person_id
    WHERE 
        ca.nr_order IS NOT NULL
    GROUP BY 
        ca.movie_id, a.name
),
MovieCompanies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS rn
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    rm.title,
    rm.production_year,
    COALESCE(actors.name, 'No Actor') AS actor_name,
    COALESCE(actors.role_count, 0) AS total_roles,
    COALESCE(movies.company_name, 'No Company') AS production_company,
    COALESCE(movies.company_type, 'N/A') AS type_of_company
FROM 
    RankedMovies rm
LEFT JOIN 
    Actors actors ON rm.title_id = actors.movie_id
LEFT JOIN 
    MovieCompanies movies ON rm.title_id = movies.movie_id AND movies.rn = 1
WHERE 
    rm.year_rank <= 3;
