WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorMovieCounts AS (
    SELECT 
        ci.person_id,
        COUNT(DISTINCT ci.movie_id) AS movie_count
    FROM 
        cast_info ci
    INNER JOIN 
        RankedMovies rm ON ci.movie_id = rm.movie_id
    GROUP BY 
        ci.person_id
),
TopActors AS (
    SELECT 
        amc.person_id,
        amc.movie_count,
        RANK() OVER (ORDER BY amc.movie_count DESC) AS actor_rank
    FROM 
        ActorMovieCounts amc
    WHERE 
        amc.movie_count > 0
),
ActorNames AS (
    SELECT 
        a.id AS person_id,
        a.name,
        aa.name AS aka_name
    FROM 
        name a
    LEFT JOIN 
        aka_name aa ON a.id = aa.person_id
    WHERE 
        a.gender = 'M'
)
SELECT 
    tn.movie_id,
    tn.title,
    tn.production_year,
    COALESCE(an.name, an.aka_name) AS actor_name,
    ta.actor_rank
FROM 
    RankedMovies tn
LEFT JOIN 
    cast_info ci ON tn.movie_id = ci.movie_id
LEFT JOIN 
    TopActors ta ON ci.person_id = ta.person_id
LEFT JOIN 
    ActorNames an ON ci.person_id = an.person_id
WHERE 
    tn.title ILIKE '%adventure%'
    AND tn.production_year BETWEEN 2000 AND 2023
    AND (ta.movie_count IS NULL OR ta.actor_rank <= 10);
