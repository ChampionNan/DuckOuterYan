
WITH RECURSIVE movie_hierarchy AS (
    
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        NULL AS parent_id,
        1 AS level
    FROM
        title t
    WHERE
        t.episode_of_id IS NULL
    
    UNION ALL

    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        mh.movie_id AS parent_id,
        mh.level + 1
    FROM
        title t
    JOIN
        movie_hierarchy mh ON t.episode_of_id = mh.movie_id
),

movie_details AS (
    SELECT
        mh.movie_id,
        mh.title,
        mh.production_year,
        COALESCE(a.name, 'Unknown') AS actor_name,
        COALESCE(c.kind, 'Not Provided') AS cast_type,
        COUNT(DISTINCT mi.info) AS info_count
    FROM
        movie_hierarchy mh
    LEFT JOIN
        complete_cast cc ON mh.movie_id = cc.movie_id
    LEFT JOIN
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN
        aka_name a ON ci.person_id = a.person_id
    LEFT JOIN
        comp_cast_type c ON ci.role_id = c.id
    LEFT JOIN
        movie_info mi ON mh.movie_id = mi.movie_id
    GROUP BY
        mh.movie_id, mh.title, mh.production_year, a.name, c.kind
)

SELECT
    md.movie_id,
    md.title,
    md.production_year,
    md.actor_name,
    md.cast_type,
    md.info_count,
    RANK() OVER (PARTITION BY md.production_year ORDER BY md.info_count DESC) AS rank_by_info_count,
    CASE 
        WHEN md.info_count IS NULL THEN 'No Info'
        ELSE 'Has Info'
    END AS info_status
FROM
    movie_details md
WHERE
    md.production_year > 2000;
