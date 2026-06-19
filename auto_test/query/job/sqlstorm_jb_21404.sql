
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_in_year,
        COUNT(*) OVER (PARTITION BY t.production_year) AS total_movies_in_year
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
TopMovies AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year, 
        rm.rank_in_year,
        rm.total_movies_in_year
    FROM 
        RankedMovies rm
    WHERE 
        rm.rank_in_year <= 5  
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
MovieDetails AS (
    SELECT 
        tm.movie_id, 
        tm.title, 
        tm.production_year, 
        COALESCE(ac.actor_count, 0) AS actor_count,
        COALESCE(m.id, 0) AS company_id,
        COALESCE(c.name, 'No Company') AS company_name,
        rm.total_movies_in_year
    FROM 
        TopMovies tm
    LEFT JOIN 
        ActorCounts ac ON tm.movie_id = ac.movie_id
    LEFT JOIN 
        movie_companies m ON tm.movie_id = m.movie_id
    LEFT JOIN 
        company_name c ON m.company_id = c.id
    LEFT JOIN 
        RankedMovies rm ON tm.movie_id = rm.movie_id
),
FinalOutput AS (
    SELECT 
        md.title,
        md.production_year,
        md.actor_count,
        md.company_name,
        CASE 
            WHEN md.actor_count > 10 THEN 'Ensemble Cast'
            WHEN md.actor_count BETWEEN 6 AND 10 THEN 'Moderate Cast'
            ELSE 'Small Cast'
        END AS cast_size,
        CONCAT('Total Movies in Year: ', md.total_movies_in_year) AS year_summary
    FROM 
        MovieDetails md
)
SELECT 
    fo.title,
    fo.production_year,
    fo.actor_count,
    fo.company_name,
    fo.cast_size,
    fo.year_summary
FROM 
    FinalOutput fo
WHERE 
    fo.company_name IS NOT NULL;
