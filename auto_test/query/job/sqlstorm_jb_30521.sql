
WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ml.linked_movie_id,
        1 AS level
    FROM
        title mt
    LEFT JOIN
        movie_link ml ON mt.id = ml.movie_id
    WHERE
        mt.production_year > 2000  

    UNION ALL

    SELECT 
        mh.movie_id,
        mt.title,
        mt.production_year,
        ml.linked_movie_id,
        mh.level + 1
    FROM 
        movie_hierarchy mh
    JOIN 
        movie_link ml ON mh.linked_movie_id = ml.movie_id
    JOIN 
        title mt ON ml.linked_movie_id = mt.id
    WHERE 
        mh.level < 3  
),

actor_movies AS (
    SELECT 
        ak.person_id AS actor_id,
        ak.name AS actor_name,
        mt.production_year,
        COUNT(DISTINCT mi.movie_id) AS movie_count
    FROM
        aka_name ak
    JOIN 
        cast_info ci ON ak.person_id = ci.person_id
    JOIN 
        title mt ON ci.movie_id = mt.id
    LEFT JOIN 
        movie_info mi ON mt.id = mi.movie_id AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'BoxOffice')
    WHERE 
        ak.name IS NOT NULL
    GROUP BY 
        ak.person_id, ak.name, mt.production_year
),

joined_data AS (
    SELECT 
        mh.title AS movie_title,
        mh.production_year,
        am.actor_name,
        am.movie_count,
        ROW_NUMBER() OVER (PARTITION BY mh.production_year ORDER BY mh.production_year DESC) AS year_rank
    FROM 
        movie_hierarchy mh
    JOIN 
        actor_movies am ON mh.movie_id = am.actor_id
)

SELECT 
    jd.movie_title,
    jd.production_year,
    jd.actor_name,
    jd.movie_count,
    jd.year_rank
FROM 
    joined_data jd
WHERE 
    jd.year_rank <= 5;
