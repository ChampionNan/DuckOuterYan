
WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank,
        COALESCE(b.name, 'Unknown') AS director_name
    FROM 
        aka_title a
    LEFT JOIN 
        movie_companies mc ON a.id = mc.movie_id
    LEFT JOIN 
        company_name b ON mc.company_id = b.id AND mc.company_type_id = (SELECT id FROM company_type WHERE kind = 'Director')
    WHERE 
        a.production_year IS NOT NULL
),
ActorMovieCount AS (
    SELECT 
        c.movie_id, 
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
FinalResults AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        rm.director_name,
        COALESCE(am.actor_count, 0) AS total_actors
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorMovieCount am ON rm.movie_id = am.movie_id
    WHERE 
        rm.year_rank <= 5
)
SELECT 
    title,
    production_year,
    director_name,
    total_actors,
    CASE 
        WHEN total_actors > 10 THEN 'Large Cast'
        WHEN total_actors BETWEEN 5 AND 10 THEN 'Medium Cast'
        ELSE 'Small Cast' 
    END AS cast_size
FROM 
    FinalResults;
