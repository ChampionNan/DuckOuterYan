WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC, ak.name) AS rank_within_year,
        COUNT(*) OVER (PARTITION BY t.production_year) AS total_movies
    FROM 
        aka_title t
    LEFT JOIN 
        aka_name ak ON t.id = ak.id
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoleCounts AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        cast_info ci
    WHERE 
        ci.note IS NOT NULL
    GROUP BY 
        ci.movie_id
),
MovieDetails AS (
    SELECT 
        r.movie_id,
        r.title,
        r.production_year,
        COALESCE(ac.actor_count, 0) AS actor_count,
        r.rank_within_year,
        r.total_movies
    FROM 
        RankedMovies r
    LEFT JOIN 
        ActorRoleCounts ac ON r.movie_id = ac.movie_id
)
SELECT 
    md.title,
    md.production_year,
    md.actor_count,
    md.rank_within_year,
    md.total_movies,
    CASE 
        WHEN md.actor_count > 10 THEN 'Big Cast'
        WHEN md.actor_count > 5 THEN 'Medium Cast'
        ELSE 'Small Cast'
    END AS cast_size_category
FROM 
    MovieDetails md
WHERE 
    md.rank_within_year = 1 
    AND md.actor_count IS NOT NULL;
