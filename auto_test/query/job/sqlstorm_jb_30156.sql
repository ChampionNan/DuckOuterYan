WITH RECURSIVE ActorHierarchy AS (
    SELECT 
        c.person_id,
        c.movie_id,
        c.nr_order,
        1 AS level
    FROM 
        cast_info c
    WHERE 
        c.nr_order = 1
    
    UNION ALL
    
    SELECT 
        c.person_id,
        c.movie_id,
        c.nr_order,
        ah.level + 1
    FROM 
        cast_info c
    JOIN 
        ActorHierarchy ah ON c.movie_id = ah.movie_id AND c.nr_order = ah.nr_order + 1
),
MovieGenres AS (
    SELECT 
        mt.movie_id,
        string_agg(DISTINCT kt.keyword, ', ') AS genres
    FROM 
        movie_keyword mk
    JOIN 
        keyword kt ON mk.keyword_id = kt.id
    JOIN 
        aka_title mt ON mk.movie_id = mt.id
    GROUP BY 
        mt.movie_id
),
MovieInfo AS (
    SELECT 
        m.title,
        m.production_year,
        a.person_id,
        a.nr_order,
        COALESCE(CAST(mg.genres AS text), 'Unknown') AS genres
    FROM 
        aka_title m
    LEFT JOIN 
        ActorHierarchy a ON m.id = a.movie_id
    LEFT JOIN 
        MovieGenres mg ON m.id = mg.movie_id
    WHERE 
        m.production_year >= 2000
),
FilteredResults AS (
    SELECT 
        mi.title,
        mi.production_year,
        mi.person_id,
        COUNT(*) OVER (PARTITION BY mi.production_year) AS actor_count,
        RANK() OVER (PARTITION BY mi.production_year ORDER BY mi.person_id) AS actor_rank
    FROM 
        MovieInfo mi
    WHERE 
        mi.genres LIKE '%Drama%' OR mi.genres LIKE '%Comedy%'
)

SELECT 
    fr.title,
    fr.production_year,
    fr.person_id,
    fr.actor_count,
    fr.actor_rank
FROM 
    FilteredResults fr
WHERE 
    fr.actor_rank <= 3;
