
WITH RECURSIVE movie_hierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS depth,
        CAST(mt.title AS VARCHAR(255)) AS path
    FROM
        aka_title mt
    WHERE
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT
        mt.id,
        mt.title,
        mt.production_year,
        mh.depth + 1,
        mh.path || ' -> ' || mt.title
    FROM
        aka_title mt
    JOIN
        movie_hierarchy mh ON mt.episode_of_id = mh.movie_id
),

top_movies AS (
    SELECT
        mh.movie_id,
        mh.title,
        mh.production_year,
        mh.depth,
        ROW_NUMBER() OVER (PARTITION BY mh.depth ORDER BY mh.production_year DESC) AS rank
    FROM
        movie_hierarchy mh
    WHERE
        mh.depth <= 3
)

SELECT
    DISTINCT p.name,
    t.title,
    t.production_year,
    c.role_id,
    CASE 
        WHEN mi.info IS NOT NULL THEN mi.info 
        ELSE 'No Info' 
    END AS additional_info,
    COALESCE(k.keyword, 'No Keywords') AS keyword
FROM
    aka_name p
JOIN
    cast_info c ON p.person_id = c.person_id
JOIN
    top_movies t ON c.movie_id = t.movie_id
LEFT JOIN
    movie_info mi ON t.movie_id = mi.movie_id
LEFT JOIN
    movie_keyword mk ON t.movie_id = mk.movie_id
LEFT JOIN
    keyword k ON mk.keyword_id = k.id
WHERE
    c.nr_order < 5
    AND t.rank <= 5
GROUP BY
    p.name,
    t.title,
    t.production_year,
    c.role_id,
    mi.info,
    k.keyword;
