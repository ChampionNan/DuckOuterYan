
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        CAST(NULL AS integer) AS parent_id
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT 
        et.id AS movie_id,
        et.title,
        et.production_year,
        et.episode_of_id AS parent_id
    FROM 
        aka_title et
    INNER JOIN 
        MovieHierarchy mh ON et.episode_of_id = mh.movie_id
),
ActorMovie AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ak.name) AS actor_order,
        COUNT(*) OVER () AS total_actors,
        mt.production_year
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        aka_title mt ON ci.movie_id = mt.id
    WHERE 
        ak.name IS NOT NULL
),
MoviesWithKeywords AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        ARRAY_AGG(DISTINCT kw.keyword) AS keywords
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        movie_keyword mk ON mh.movie_id = mk.movie_id
    LEFT JOIN 
        keyword kw ON mk.keyword_id = kw.id
    GROUP BY 
        mh.movie_id, mh.title, mh.production_year
)
SELECT 
    am.movie_id,
    mh.title,
    mh.production_year,
    am.actor_name,
    am.actor_order,
    am.total_actors,
    mwk.keywords
FROM 
    ActorMovie am
JOIN 
    MoviesWithKeywords mwk ON am.movie_id = mwk.movie_id
JOIN 
    MovieHierarchy mh ON am.movie_id = mh.movie_id
WHERE 
    mwk.keywords IS NOT NULL;
