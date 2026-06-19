WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_per_year
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorCounts AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.movie_id
),
CompanyDetails AS (
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
    WHERE 
        c.country_code IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        ac.actor_count,
        COALESCE(cd.company_name, 'No Company') AS company_name,
        COALESCE(cd.company_type, 'Unknown') AS company_type
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorCounts ac ON rm.movie_id = ac.movie_id
    LEFT JOIN 
        CompanyDetails cd ON rm.movie_id = cd.movie_id
    WHERE 
        rm.rank_per_year <= 5
)
SELECT 
    f.title,
    f.production_year,
    f.actor_count,
    f.company_name,
    f.company_type,
    CASE 
        WHEN f.actor_count IS NULL THEN 'No Actors'
        WHEN f.actor_count > 10 THEN 'Star-Studded'
        ELSE 'Average Cast'
    END AS cast_description
FROM 
    FilteredMovies f;
