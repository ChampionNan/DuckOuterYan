WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        aka_title t
    WHERE 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie')
),
ActorInfo AS (
    SELECT 
        ca.movie_id,
        a.name AS actor_name,
        RANK() OVER (PARTITION BY ca.movie_id ORDER BY ca.nr_order) AS actor_rank
    FROM 
        cast_info ca
    JOIN aka_name a ON ca.person_id = a.person_id
    WHERE 
        ca.nr_order IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year,
        COUNT(ai.actor_name) AS actor_count
    FROM 
        RankedMovies rm
    LEFT JOIN ActorInfo ai ON rm.movie_id = ai.movie_id
    WHERE 
        rm.rank <= 5
    GROUP BY 
        rm.movie_id, rm.title, rm.production_year
)
SELECT 
    fm.movie_id, 
    fm.title, 
    fm.production_year,
    COALESCE(fm.actor_count, 0) AS actor_count,
    CASE 
        WHEN fm.actor_count IS NULL THEN 'No Actors Available'
        WHEN fm.actor_count > 5 THEN 'Many Actors'
        ELSE 'Few Actors'
    END AS actor_availability
FROM 
    FilteredMovies fm
LEFT JOIN movie_info mi ON fm.movie_id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Genre')
WHERE 
    (mi.info IS NULL OR mi.info LIKE '%Drama%');
