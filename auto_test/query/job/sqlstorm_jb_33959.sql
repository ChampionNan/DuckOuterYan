
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS movie_title,
        1 AS level,
        NULL AS parent_movie_id
    FROM 
        aka_title AS mt
    WHERE 
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT 
        e.id AS movie_id,
        e.title AS movie_title,
        mh.level + 1 AS level,
        mh.movie_id AS parent_movie_id
    FROM 
        aka_title AS e
    JOIN 
        MovieHierarchy AS mh ON e.episode_of_id = mh.movie_id
),

ActorRoles AS (
    SELECT 
        p.id AS person_id,
        ak.name AS actor_name,
        r.role AS role_name,
        c.movie_id,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY p.id) AS role_order
    FROM 
        cast_info AS c
    JOIN 
        aka_name AS ak ON c.person_id = ak.person_id
    JOIN 
        role_type AS r ON c.role_id = r.id
    JOIN 
        name AS p ON ak.person_id = p.imdb_id
),

MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword AS mk
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)

SELECT 
    h.movie_title,
    a.actor_name,
    a.role_name,
    COALESCE(mk.keywords, 'No keywords') AS keywords,
    h.level AS hierarchy_level
FROM 
    MovieHierarchy AS h
LEFT JOIN 
    ActorRoles AS a ON h.movie_id = a.movie_id
LEFT JOIN 
    MovieKeywords AS mk ON h.movie_id = mk.movie_id
WHERE 
    h.level <= 2 
    AND a.role_name IS NOT NULL;
