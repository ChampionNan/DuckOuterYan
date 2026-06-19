
WITH RankedMovies AS (
    SELECT 
        a.title AS movie_title,
        a.production_year,
        r.role AS person_role,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS year_rank
    FROM 
        aka_title a
    JOIN 
        cast_info c ON a.id = c.movie_id
    JOIN 
        role_type r ON c.role_id = r.id
    WHERE 
        a.production_year IS NOT NULL
),
TopRankedMovies AS (
    SELECT 
        movie_title,
        production_year,
        person_role
    FROM 
        RankedMovies
    WHERE 
        year_rank = 1
),
MovieCompanies AS (
    SELECT 
        m.movie_id,
        COALESCE(c.name, 'Unknown') AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies m
    LEFT JOIN 
        company_name c ON m.company_id = c.id
    LEFT JOIN 
        company_type ct ON m.company_type_id = ct.id
)
SELECT 
    m.movie_title,
    m.production_year,
    m.person_role,
    mc.company_name,
    mc.company_type
FROM 
    TopRankedMovies m
FULL OUTER JOIN 
    MovieCompanies mc ON m.movie_title = mc.movie_id::text
WHERE 
    (m.person_role IS NULL OR mc.company_name IS NOT NULL);
