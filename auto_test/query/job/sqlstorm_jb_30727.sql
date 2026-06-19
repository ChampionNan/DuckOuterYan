
WITH RECURSIVE CastHierarchy AS (
    SELECT
        c.movie_id,
        c.person_id,
        1 AS depth
    FROM
        cast_info c
    WHERE
        c.person_role_id = (SELECT id FROM role_type WHERE role = 'Actor')

    UNION ALL

    SELECT
        c.movie_id,
        c.person_id,
        ch.depth + 1
    FROM
        cast_info c
    JOIN
        CastHierarchy ch ON c.movie_id = ch.movie_id
    WHERE
        c.person_id != ch.person_id
),

MovieActorInfo AS (
    SELECT
        m.id AS movie_id,
        m.title,
        a.name AS actor_name,
        ch.depth,
        COUNT(*) OVER (PARTITION BY m.id) AS total_cast,
        COALESCE(i.info, 'No info available') AS movie_info,
        ARRAY_AGG(DISTINCT k.keyword) AS keywords
    FROM
        aka_title m
    LEFT JOIN
        cast_info ca ON m.id = ca.movie_id
    LEFT JOIN
        aka_name a ON ca.person_id = a.person_id
    LEFT JOIN
        movie_info i ON m.id = i.movie_id AND i.info_type_id = (SELECT id FROM info_type WHERE info = 'Synopsis')
    LEFT JOIN
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN
        CastHierarchy ch ON ch.movie_id = m.id
    WHERE
        m.production_year >= 2000
    GROUP BY
        m.id, m.title, a.name, ch.depth, i.info
)

SELECT
    m.movie_id,
    m.title,
    m.actor_name,
    m.depth,
    m.total_cast,
    m.movie_info,
    m.keywords,
    CASE
        WHEN m.total_cast > 5 THEN 'Ensemble Cast'
        WHEN m.total_cast BETWEEN 3 AND 5 THEN 'Moderate Cast'
        ELSE 'Solo Cast'
    END AS cast_size_category
FROM
    MovieActorInfo m;
