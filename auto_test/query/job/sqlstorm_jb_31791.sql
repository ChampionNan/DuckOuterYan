
WITH RECURSIVE MovieHierarchy AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        1 AS level
    FROM
        aka_title t
    WHERE
        t.production_year > 2000 

    UNION ALL

    SELECT
        m.linked_movie_id,
        t.title,
        t.production_year,
        mh.level + 1
    FROM
        movie_link m
    JOIN
        title t ON m.linked_movie_id = t.id
    JOIN
        MovieHierarchy mh ON mh.movie_id = m.movie_id
    WHERE
        mh.level < 5 
),
RankedMovies AS (
    SELECT
        mh.movie_id,
        mh.title,
        mh.production_year,
        RANK() OVER (PARTITION BY mh.production_year ORDER BY mh.title) AS rank
    FROM
        MovieHierarchy mh
),
MovieDetails AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(ka.name, 'Unknown') AS main_actor,
        COUNT(DISTINCT mc.company_id) AS company_count,
        r.role AS role_description
    FROM
        RankedMovies rm
    LEFT JOIN
        cast_info ci ON rm.movie_id = ci.movie_id
    LEFT JOIN
        aka_name ka ON ci.person_id = ka.person_id
    LEFT JOIN
        movie_companies mc ON rm.movie_id = mc.movie_id
    LEFT JOIN
        role_type r ON ci.role_id = r.id
    GROUP BY
        rm.movie_id, rm.title, rm.production_year, ka.name, r.role
)
SELECT
    md.movie_id,
    md.title,
    md.production_year,
    md.main_actor,
    md.company_count,
    CASE
        WHEN md.company_count > 5 THEN 'Major Production'
        WHEN md.company_count IS NULL THEN 'No Companies'
        ELSE 'Independent'
    END AS production_scale,
    md.role_description
FROM
    MovieDetails md
JOIN
    RankedMovies rm ON md.movie_id = rm.movie_id
WHERE
    md.production_year BETWEEN 2000 AND 2020
AND
    rm.rank <= 10;
