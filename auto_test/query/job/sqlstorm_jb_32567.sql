
WITH RECURSIVE movie_hierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        NULL AS parent_movie_id,
        1 AS level
    FROM
        aka_title mt
    WHERE
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT
        mt.id AS movie_id,
        mt.title,
        mh.movie_id AS parent_movie_id,
        mh.level + 1
    FROM
        aka_title mt
    JOIN
        movie_hierarchy mh ON mt.episode_of_id = mh.movie_id
),
cast_and_roles AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        rt.role AS role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM
        cast_info ci
    JOIN
        aka_name ak ON ci.person_id = ak.person_id
    JOIN
        role_type rt ON ci.role_id = rt.id
),
movie_keywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
),
movie_details AS (
    SELECT
        mh.movie_id,
        mh.title,
        mh.parent_movie_id,
        mh.level,
        COALESCE(ki.keywords, 'No keywords') AS keywords,
        COALESCE(ca.actor_name, 'Unknown') AS primary_actor,
        COALESCE(ca.role, 'Unknown Role') AS primary_role
    FROM
        movie_hierarchy mh
    LEFT JOIN 
        movie_keywords ki ON mh.movie_id = ki.movie_id
    LEFT JOIN 
        (
            SELECT
                movie_id,
                actor_name,
                role
            FROM 
                cast_and_roles
            WHERE 
                actor_order = 1
        ) ca ON mh.movie_id = ca.movie_id
)
SELECT
    md.movie_id,
    md.title,
    md.parent_movie_id,
    md.level,
    md.keywords,
    md.primary_actor,
    md.primary_role
FROM
    movie_details md
JOIN 
    aka_title a ON md.movie_id = a.id
WHERE
    md.level = 1
    AND (md.keywords IS NOT NULL OR md.primary_actor IS NOT NULL);
