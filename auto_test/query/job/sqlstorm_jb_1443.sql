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
ActorAwards AS (
    SELECT 
        ci.person_id, 
        COUNT(DISTINCT ci.movie_id) AS award_count
    FROM 
        cast_info ci
    JOIN 
        movie_info mi ON ci.movie_id = mi.movie_id
    JOIN 
        info_type it ON mi.info_type_id = it.id
    WHERE 
        it.info ILIKE '%award%'
    GROUP BY 
        ci.person_id
),
FilteredActors AS (
    SELECT 
        ak.name,
        ak.id AS actor_id,
        aa.award_count
    FROM 
        aka_name ak
    LEFT JOIN 
        ActorAwards aa ON ak.person_id = aa.person_id
    WHERE 
        aa.award_count IS NOT NULL OR ak.name ILIKE '%Smith%'
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    fa.name AS actor_name,
    fa.award_count
FROM 
    RankedMovies rm
LEFT JOIN 
    cast_info ci ON rm.movie_id = ci.movie_id
LEFT JOIN 
    FilteredActors fa ON ci.person_id = fa.actor_id
WHERE 
    (fa.award_count > 2 OR fa.actor_id IS NULL);
