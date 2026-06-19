WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_per_year
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorMovieCount AS (
    SELECT 
        ci.person_id,
        COUNT(DISTINCT ci.movie_id) AS movie_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.person_id
),
SelectActors AS (
    SELECT 
        a.id AS actor_id,
        a.name,
        ac.movie_count
    FROM 
        aka_name a
    JOIN 
        ActorMovieCount ac ON a.person_id = ac.person_id
    WHERE 
        ac.movie_count > 5 
)
SELECT 
    r.movie_id,
    r.title,
    r.production_year,
    COALESCE(sa.name, 'Unknown Actor') AS actor_name,
    r.rank_per_year
FROM 
    RankedMovies r
LEFT JOIN 
    movie_companies mc ON r.movie_id = mc.movie_id
LEFT JOIN 
    SelectActors sa ON mc.company_id = sa.actor_id
WHERE 
    r.rank_per_year <= 10;
