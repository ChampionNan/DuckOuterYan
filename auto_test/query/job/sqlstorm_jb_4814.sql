WITH RankedMovies AS (
    SELECT 
        title.id AS movie_id,
        title.title,
        title.production_year,
        ROW_NUMBER() OVER (PARTITION BY title.production_year ORDER BY title.title) AS rank
    FROM 
        title
    WHERE 
        title.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
),
TopMovies AS (
    SELECT 
        movie_id, 
        title, 
        production_year
    FROM 
        RankedMovies 
    WHERE 
        rank <= 10
),
CastDetails AS (
    SELECT 
        ca.movie_id,
        a.name AS actor_name,
        COALESCE(role.role, 'Unknown') AS role
    FROM 
        cast_info ca
    LEFT JOIN 
        aka_name a ON ca.person_id = a.person_id
    LEFT JOIN 
        role_type role ON ca.role_id = role.id
),
MovieCompanyInfo AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(cn.name, ', ') AS companies
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    GROUP BY 
        mc.movie_id
)
SELECT 
    tm.title,
    tm.production_year,
    cd.actor_name,
    cd.role,
    mci.companies
FROM 
    TopMovies tm
LEFT JOIN 
    CastDetails cd ON tm.movie_id = cd.movie_id
LEFT JOIN 
    MovieCompanyInfo mci ON tm.movie_id = mci.movie_id
WHERE 
    (cd.role IS NOT NULL OR mci.companies IS NOT NULL);
