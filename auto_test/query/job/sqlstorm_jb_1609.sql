
WITH RankedTitles AS (
    SELECT 
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank
    FROM 
        aka_title a
    WHERE 
        a.production_year IS NOT NULL
),
ActorCount AS (
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
        m.id AS movie_id,
        m.title,
        CASE 
            WHEN m.production_year IS NULL THEN 'Unknown' 
            ELSE CAST(m.production_year AS VARCHAR) 
        END AS release_year,
        COALESCE(ac.actor_count, 0) AS actor_count,
        COALESCE(kw.keyword, 'None') AS keyword
    FROM 
        aka_title m
    LEFT JOIN 
        ActorCount ac ON m.id = ac.movie_id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword kw ON mk.keyword_id = kw.id
)
SELECT 
    md.title,
    md.release_year,
    md.actor_count,
    RANK() OVER (ORDER BY md.actor_count DESC) AS actor_rank,
    COUNT(*) OVER () AS total_movies,
    CASE 
        WHEN md.release_year = 'Unknown' THEN 'Not Available' 
        ELSE md.release_year 
    END AS adjusted_release_year
FROM 
    MovieDetails md
WHERE 
    md.actor_count > 0
GROUP BY 
    md.title, md.release_year, md.actor_count;
