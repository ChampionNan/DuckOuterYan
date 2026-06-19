
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(*) OVER (PARTITION BY t.production_year) AS title_count
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorNames AS (
    SELECT 
        ak.person_id,
        STRING_AGG(ak.name, ', ') AS actor_names
    FROM 
        aka_name ak
    JOIN 
        cast_info ci ON ak.person_id = ci.person_id
    GROUP BY 
        ak.person_id
),
MoviesWithActors AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        an.actor_names
    FROM 
        RankedMovies rm
    LEFT JOIN 
        cast_info ci ON rm.movie_id = ci.movie_id
    LEFT JOIN 
        ActorNames an ON ci.person_id = an.person_id
)
SELECT 
    m.title,
    m.production_year,
    CASE 
        WHEN COUNT(m.movie_id) OVER (PARTITION BY m.production_year) > 1 THEN 'Multiple Titles'
        ELSE 'Sole Title'
    END AS title_type,
    m.actor_names,
    COALESCE(m.production_year, 0) AS production_year_null_check
FROM 
    MoviesWithActors m
WHERE 
    NOT EXISTS (
        SELECT 1 
        FROM movie_keyword mk 
        WHERE mk.movie_id = m.movie_id 
        AND mk.keyword_id IN (
            SELECT id 
            FROM keyword 
            WHERE keyword LIKE '%bizarre%'
        )
    )
    AND (m.production_year IS NOT NULL OR m.actor_names IS NOT NULL);
