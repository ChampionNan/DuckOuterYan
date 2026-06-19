
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        1 AS level,
        NULL AS parent_id
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        mh.level + 1 AS level,
        mh.movie_id AS parent_id
    FROM 
        aka_title mt
    JOIN 
        MovieHierarchy mh ON mt.episode_of_id = mh.movie_id
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        an.name AS actor_name,
        ci.nr_order,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name an ON ci.person_id = an.person_id
),
MovieInfo AS (
    SELECT 
        mi.movie_id,
        STRING_AGG(DISTINCT mi.info, '; ') AS info_details
    FROM 
        movie_info mi
    WHERE 
        mi.note IS NULL 
    GROUP BY 
        mi.movie_id
),
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.movie_title,
        COALESCE(cd.actor_name, 'Unknown Actor') AS main_actor,
        mi.info_details,
        mh.level
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        CastDetails cd ON mh.movie_id = cd.movie_id AND cd.actor_rank = 1 
    LEFT JOIN 
        MovieInfo mi ON mh.movie_id = mi.movie_id
)
SELECT 
    rm.movie_id,
    rm.movie_title,
    rm.main_actor,
    rm.info_details,
    rm.level,
    CASE 
        WHEN rm.level = 1 THEN 'Top Level Movie'
        ELSE 'Sub Movie'
    END AS movie_category
FROM 
    RankedMovies rm
WHERE 
    rm.info_details IS NOT NULL;
