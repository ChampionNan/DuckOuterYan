WITH RankedMovies AS (
    SELECT 
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
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
)
SELECT 
    rm.title,
    rm.production_year,
    rm.keyword,
    coalesce(ac.actor_count, 0) AS actor_count,
    CASE 
        WHEN ac.actor_count IS NULL THEN 'No actors'
        WHEN ac.actor_count > 10 THEN 'Large cast'
        ELSE 'Small cast'
    END AS cast_size_category
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorCounts ac ON rm.title = (SELECT title FROM aka_title WHERE id = ac.movie_id)
WHERE 
    rm.year_rank <= 5;
