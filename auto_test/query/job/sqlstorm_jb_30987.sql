
WITH RECURSIVE movie_hierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        mt.kind_id,
        1 AS level
    FROM
        aka_title mt
    WHERE
        mt.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
    UNION ALL
    SELECT
        ml.linked_movie_id AS movie_id,
        at.title,
        at.production_year,
        at.kind_id,
        mh.level + 1
    FROM
        movie_link ml
    JOIN aka_title at ON ml.linked_movie_id = at.id
    JOIN movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 3  
),
actor_movies AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ak.name) AS actor_order
    FROM
        cast_info ci
    JOIN aka_name ak ON ci.person_id = ak.person_id
),
movie_keywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
),
completed_movies AS (
    SELECT DISTINCT
        mh.movie_id,
        mh.title,
        mh.production_year,
        ak.actor_name,
        mk.keywords,
        mh.level,
        ci.note AS role_note
    FROM
        movie_hierarchy mh
    LEFT JOIN actor_movies ak ON mh.movie_id = ak.movie_id
    LEFT JOIN movie_keywords mk ON mh.movie_id = mk.movie_id
    LEFT JOIN cast_info ci ON mh.movie_id = ci.movie_id
    WHERE
        mh.production_year >= 2000
        AND (ci.note IS NULL OR ci.note != 'uncredited')
),
ranked_movies AS (
    SELECT
        cm.*,
        RANK() OVER (PARTITION BY cm.production_year ORDER BY cm.level, cm.title) AS rank_in_year
    FROM
        completed_movies cm
)
SELECT
    movie_id,
    title,
    production_year,
    actor_name,
    keywords,
    level,
    rank_in_year
FROM
    ranked_movies
WHERE
    rank_in_year <= 5;
