
WITH RECURSIVE movie_hierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title AS movie_title,
        mt.production_year,
        CAST(NULL AS VARCHAR) AS parent_movie,
        0 AS level
    FROM
        aka_title mt
    WHERE
        mt.episode_of_id IS NULL  

    UNION ALL

    SELECT
        m.id AS movie_id,
        m.title AS movie_title,
        m.production_year,
        mh.movie_title AS parent_movie,
        mh.level + 1
    FROM
        aka_title m
    JOIN movie_hierarchy mh ON m.episode_of_id = mh.movie_id
),

movie_details AS (
    SELECT
        mh.movie_id,
        mh.movie_title,
        mh.production_year,
        mr.name AS director_name,
        cct.kind AS cast_type,
        ROW_NUMBER() OVER (PARTITION BY mh.movie_id ORDER BY cct.kind) AS role_rank
    FROM
        movie_hierarchy mh
    LEFT JOIN complete_cast cc ON mh.movie_id = cc.movie_id
    LEFT JOIN cast_info ci ON cc.subject_id = ci.id
    LEFT JOIN aka_name mr ON ci.person_id = mr.person_id AND ci.role_id IN (SELECT id FROM role_type WHERE role = 'Director')
    LEFT JOIN comp_cast_type cct ON ci.person_role_id = cct.id
    WHERE
        mh.production_year > 2000  
),

keyword_details AS (
    SELECT
        md.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM
        movie_keyword mk
    JOIN movie_details md ON mk.movie_id = md.movie_id
    GROUP BY
        md.movie_id
),

final_output AS (
    SELECT
        md.movie_id,
        md.movie_title,
        md.production_year,
        COALESCE(md.director_name, 'Unknown') AS director_name,
        COALESCE(kd.keyword_count, 0) AS keyword_count,
        mh.level AS movie_level
    FROM
        movie_details md
    LEFT JOIN keyword_details kd ON md.movie_id = kd.movie_id
    JOIN movie_hierarchy mh ON md.movie_id = mh.movie_id
)

SELECT
    *
FROM
    final_output
WHERE
    movie_level = 0;
