
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        NULL AS parent_id
    FROM 
        aka_title AS m
    WHERE 
        m.episode_of_id IS NULL

    UNION ALL

    SELECT 
        e.id AS movie_id,
        e.title AS movie_title,
        e.production_year,
        mh.movie_id AS parent_id
    FROM 
        aka_title AS e
    JOIN movie_hierarchy AS mh ON e.episode_of_id = mh.movie_id
),
cast_with_roles AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS role_rank
    FROM 
        cast_info AS c
    JOIN aka_name AS a ON c.person_id = a.person_id
    JOIN role_type AS r ON c.role_id = r.id
),
movies_with_cast AS (
    SELECT 
        mh.movie_id,
        mh.movie_title,
        mh.production_year,
        COALESCE(cwr.actor_name, 'Unknown Actor') AS actor_name,
        COALESCE(cwr.role_name, 'Unknown Role') AS role_name,
        cwr.role_rank
    FROM 
        movie_hierarchy AS mh
    LEFT JOIN cast_with_roles AS cwr ON mh.movie_id = cwr.movie_id
),
favorites AS (
    SELECT 
        DISTINCT m.movie_id,
        m.movie_title
    FROM 
        movies_with_cast AS m
    WHERE 
        m.actor_name LIKE '%Clooney%'
)
SELECT 
    m.movie_id,
    m.movie_title,
    m.production_year,
    COALESCE(agg.actors, 'None') AS actors_in_movie
FROM 
    movies_with_cast AS m
LEFT JOIN (
    SELECT 
        movie_id,
        STRING_AGG(actor_name, ', ') AS actors
    FROM 
        movies_with_cast
    WHERE 
        role_rank <= 3
    GROUP BY 
        movie_id
) AS agg ON m.movie_id = agg.movie_id
WHERE 
    m.movie_id IN (SELECT movie_id FROM favorites)
    AND m.production_year >= 2000
GROUP BY 
    m.movie_id, m.movie_title, m.production_year, agg.actors;
