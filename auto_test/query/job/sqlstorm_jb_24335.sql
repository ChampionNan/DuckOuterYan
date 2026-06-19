
WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.title) AS rank_within_year,
        COUNT(*) OVER (PARTITION BY m.production_year) AS total_movies
    FROM 
        aka_title m
    WHERE 
        m.title IS NOT NULL
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS company_rank
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
CastInfo AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS cast_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        ci.note IS NULL
),
MoviesWithDetails AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        cd.company_name,
        cd.company_type,
        ci.actor_name,
        rm.rank_within_year,
        rm.total_movies,
        ci.cast_rank
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CompanyDetails cd ON rm.movie_id = cd.movie_id AND cd.company_rank = 1  
    LEFT JOIN 
        CastInfo ci ON rm.movie_id = ci.movie_id AND ci.cast_rank <= 3  
)
SELECT 
    m.title,
    m.production_year,
    COALESCE(m.company_name, 'No Company') AS company_name,
    COALESCE(m.actor_name, 'No Actor') AS lead_actor,
    m.rank_within_year,
    m.total_movies,
    CASE 
        WHEN m.total_movies = 0 THEN NULL
        ELSE CAST(m.rank_within_year AS FLOAT) / m.total_movies
    END AS rank_fraction
FROM 
    MoviesWithDetails m
WHERE 
    m.production_year >= 2000
GROUP BY 
    m.title,
    m.production_year,
    m.company_name,
    m.actor_name,
    m.rank_within_year,
    m.total_movies;
