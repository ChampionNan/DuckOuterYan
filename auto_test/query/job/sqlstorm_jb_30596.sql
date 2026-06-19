
WITH RECURSIVE MovieHierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS level
    FROM
        aka_title mt
    WHERE
        mt.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie') 

    UNION ALL

    SELECT
        ml.linked_movie_id AS movie_id,
        mtt.title,
        mtt.production_year,
        mh.level + 1 AS level
    FROM
        movie_link ml
    JOIN
        MovieHierarchy mh ON ml.movie_id = mh.movie_id
    JOIN
        aka_title mtt ON ml.linked_movie_id = mtt.id
)

SELECT
    ak.name AS actor_name,
    at.title AS movie_title,
    at.production_year,
    p.info AS actor_info,
    ROW_NUMBER() OVER (PARTITION BY ak.person_id ORDER BY at.production_year DESC) AS rank,
    COUNT(DISTINCT mc.company_id) AS production_companies
FROM
    cast_info ci
JOIN
    aka_name ak ON ci.person_id = ak.person_id
JOIN
    aka_title at ON ci.movie_id = at.id
LEFT JOIN
    movie_companies mc ON mc.movie_id = at.id
LEFT JOIN
    person_info p ON p.person_id = ak.person_id AND p.info_type_id IS NULL
WHERE
    ak.name IS NOT NULL
    AND at.production_year BETWEEN 2000 AND 2023
    AND at.kind_id IN (SELECT id FROM kind_type WHERE kind IN ('movie', 'tv series'))
    AND NOT EXISTS (
        SELECT 1
        FROM movie_keyword mk
        JOIN keyword k ON mk.keyword_id = k.id
        WHERE mk.movie_id = at.id AND k.keyword = 'flop'
    )
GROUP BY
    ak.name, at.title, at.production_year, p.info, ak.person_id;
