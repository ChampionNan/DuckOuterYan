WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        0 AS level
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        mh.level + 1
    FROM 
        aka_title mt
    JOIN 
        movie_hierarchy mh ON mt.episode_of_id = mh.movie_id
),

ranked_cast AS (
    SELECT 
        ci.movie_id,
        ka.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank,
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS total_actors
    FROM 
        cast_info ci
    JOIN 
        aka_name ka ON ci.person_id = ka.person_id
),

filtered_movies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        rc.actor_name,
        rc.actor_rank,
        rc.total_actors,
        COALESCE(kw.keyword, 'No Keyword') AS movie_keyword
    FROM 
        movie_hierarchy mh
    LEFT JOIN 
        ranked_cast rc ON mh.movie_id = rc.movie_id
    LEFT JOIN 
        movie_keyword mk ON mh.movie_id = mk.movie_id
    LEFT JOIN 
        keyword kw ON mk.keyword_id = kw.id
)

SELECT 
    fm.title,
    fm.production_year,
    fm.actor_name,
    fm.actor_rank,
    fm.total_actors,
    CASE 
        WHEN fm.actor_name IS NULL THEN 'No Cast Found'
        ELSE CONCAT(fm.actor_name, ' (Rank ', fm.actor_rank, ' of ', fm.total_actors, ')')
    END AS actor_info,
    COUNT(*) OVER (PARTITION BY fm.production_year) AS movies_in_year
FROM 
    filtered_movies fm
WHERE 
    fm.production_year >= 2000;
