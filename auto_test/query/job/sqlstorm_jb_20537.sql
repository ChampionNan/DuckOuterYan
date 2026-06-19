
WITH RankedMovies AS (
    SELECT 
        a.title AS movie_title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY b.nr_order) AS rn,
        COUNT(*) OVER (PARTITION BY a.production_year) AS movie_count
    FROM 
        aka_title a
    LEFT JOIN 
        (SELECT movie_id, nr_order
         FROM cast_info
         WHERE person_role_id = (SELECT id FROM role_type WHERE role = 'actor')
         ORDER BY nr_order) b ON a.id = b.movie_id
    WHERE 
        a.production_year IS NOT NULL
),
FilteredMovies AS (
    SELECT
        movie_title,
        production_year,
        rn,
        movie_count
    FROM 
        RankedMovies
    WHERE 
        rn <= 5
),
ActorCounts AS (
    SELECT 
        c.movie_id,
        COUNT(*) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
MoviesWithActorCounts AS (
    SELECT 
        fm.movie_title,
        fm.production_year,
        ac.actor_count,
        COALESCE(fm.movie_count, 0) AS total_movies
    FROM 
        FilteredMovies fm
    LEFT JOIN 
        ActorCounts ac ON fm.movie_title = (SELECT title FROM aka_title WHERE id = ac.movie_id) 
    WHERE 
        fm.movie_count > 0
)
SELECT 
    mwac.movie_title,
    mwac.production_year,
    mwac.actor_count,
    mwac.total_movies,
    CASE 
        WHEN mwac.actor_count IS NULL THEN 'No actors listed'
        ELSE 'Total actors: ' || CAST(mwac.actor_count AS VARCHAR) 
    END AS actor_description,
    CASE 
        WHEN mwac.total_movies < 5 THEN 'Fewer than expected movies in year.'
        ELSE 'Sufficient number of movies found.'
    END AS movie_count_description
FROM 
    MoviesWithActorCounts mwac
WHERE 
    mwac.actor_count IS NOT NULL;
