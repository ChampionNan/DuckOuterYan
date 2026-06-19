WITH RankedMovies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.title) AS rank
    FROM 
        aka_title mt
    WHERE 
        mt.production_year IS NOT NULL
), 
ActorMovieCount AS (
    SELECT 
        ac.person_id,
        COUNT(DISTINCT ac.movie_id) AS movie_count
    FROM 
        cast_info ac
    GROUP BY 
        ac.person_id
),
RankedActors AS (
    SELECT 
        an.id AS person_id,
        an.name,
        COALESCE(amc.movie_count, 0) AS movie_count,
        ROW_NUMBER() OVER (ORDER BY COALESCE(amc.movie_count, 0) DESC, an.name) AS actor_rank
    FROM 
        aka_name an
    LEFT JOIN 
        ActorMovieCount amc ON an.person_id = amc.person_id
)
SELECT 
    ra.name AS actor_name,
    ra.movie_count,
    RANK() OVER (ORDER BY ra.movie_count DESC) AS movie_rank,
    rm.title AS movie_title,
    rm.production_year,
    EXISTS (
        SELECT 
            1 
        FROM 
            movie_info mi 
        JOIN 
            info_type it ON mi.info_type_id = it.id 
        WHERE 
            mi.movie_id = rm.movie_id 
            AND it.info LIKE '%Award%'
    ) AS has_award_info
FROM 
    RankedActors ra
LEFT JOIN 
    RankedMovies rm ON ra.movie_count > 0
WHERE 
    ra.actor_rank <= 10 
    AND (ra.movie_count IS NULL OR ra.movie_count > 1);
