WITH RECURSIVE movie_hierarchy AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        m.kind_id,
        1 AS depth
    FROM
        aka_title m
    WHERE
        m.production_year >= 2000

    UNION ALL

    SELECT
        m.id AS movie_id,
        CONCAT('Sequel of ', mh.title) AS title,
        mh.production_year,
        mh.kind_id,
        mh.depth + 1
    FROM
        movie_link ml
    JOIN
        movie_hierarchy mh ON ml.linked_movie_id = mh.movie_id
    JOIN
        aka_title m ON ml.movie_id = m.id
    WHERE
        mh.depth < 3
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

cast_details AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS actor_role
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
)

SELECT
    mh.movie_id,
    mh.title,
    mh.production_year,
    mh.depth,
    COALESCE(mk.keywords, 'No Keywords') AS keywords,
    COALESCE(cd.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(cd.actor_role, 'No Role') AS actor_role
FROM
    movie_hierarchy mh
LEFT JOIN
    movie_keywords mk ON mh.movie_id = mk.movie_id
LEFT JOIN
    cast_details cd ON mh.movie_id = cd.movie_id
WHERE
    (mh.production_year BETWEEN 2000 AND 2023)
    AND (mh.kind_id IS NOT NULL);
