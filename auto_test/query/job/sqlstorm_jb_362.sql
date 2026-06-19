WITH RankedMovies AS (
    SELECT 
        title.id AS movie_id,
        title.title,
        title.production_year,
        ROW_NUMBER() OVER (PARTITION BY title.production_year ORDER BY title.id DESC) AS rn
    FROM 
        title
    WHERE 
        title.production_year >= 2000
),
ActorMovies AS (
    SELECT 
        aka_name.person_id,
        aka_name.name AS actor_name,
        cast_info.movie_id,
        COUNT(*) OVER (PARTITION BY aka_name.person_id) AS movie_count
    FROM 
        aka_name
    JOIN 
        cast_info ON aka_name.person_id = cast_info.person_id
),
KeywordMovies AS (
    SELECT 
        movie_keyword.movie_id,
        STRING_AGG(keyword.keyword, ', ') AS keywords
    FROM 
        movie_keyword
    JOIN 
        keyword ON movie_keyword.keyword_id = keyword.id
    GROUP BY 
        movie_keyword.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    am.actor_name,
    am.movie_count,
    km.keywords,
    COALESCE(am.movie_count, 0) AS total_movies,
    CASE 
        WHEN rm.production_year IS NULL THEN 'Unknown Year'
        ELSE CAST(rm.production_year AS TEXT)
    END AS year_info
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorMovies am ON rm.movie_id = am.movie_id
LEFT JOIN 
    KeywordMovies km ON rm.movie_id = km.movie_id
WHERE 
    rm.rn <= 10;
