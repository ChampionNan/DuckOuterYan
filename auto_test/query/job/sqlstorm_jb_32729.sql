WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS level
    FROM 
        aka_title AS mt
    WHERE 
        mt.episode_of_id IS NULL  

    UNION ALL
  
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        mh.level + 1
    FROM 
        aka_title AS mt
    JOIN 
        MovieHierarchy AS mh ON mt.episode_of_id = mh.movie_id  
),
ActorMovieCount AS (
    SELECT 
        ca.person_id,
        COUNT(DISTINCT ca.movie_id) AS movie_count
    FROM 
        cast_info AS ca
    JOIN 
        aka_title AS at ON ca.movie_id = at.id 
    WHERE 
        at.production_year IS NOT NULL
    GROUP BY 
        ca.person_id
),
RankedActors AS (
    SELECT 
        p.id AS person_id,
        a.name,
        ac.movie_count,
        RANK() OVER (ORDER BY ac.movie_count DESC) AS actor_rank
    FROM 
        aka_name AS a
    JOIN 
        ActorMovieCount AS ac ON a.person_id = ac.person_id
    JOIN 
        name AS p ON p.imdb_id = a.person_id
)
SELECT 
    mh.title AS movie_title,
    mh.production_year,
    ra.name AS actor_name,
    ra.movie_count,
    ra.actor_rank,
    CASE 
        WHEN ra.movie_count = 0 THEN 'No Roles'
        WHEN ra.actor_rank <= 10 THEN 'Top Actor'
        ELSE 'Supporting Actor'
    END AS actor_status
FROM 
    MovieHierarchy AS mh
LEFT JOIN 
    cast_info AS ci ON mh.movie_id = ci.movie_id
LEFT JOIN 
    RankedActors AS ra ON ci.person_id = ra.person_id;
