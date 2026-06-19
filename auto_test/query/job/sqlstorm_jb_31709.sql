
WITH RECURSIVE MovieHierarchy AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        0 AS level,
        NULL AS parent_movie_id
    FROM
        aka_title mt
    WHERE
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT
        et.id AS movie_id,
        et.title,
        et.production_year,
        mh.level + 1 AS level,
        mh.movie_id AS parent_movie_id
    FROM
        aka_title et
    JOIN
        MovieHierarchy mh ON et.episode_of_id = mh.movie_id
),

MovieCast AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY c.nr_order) AS actor_rank
    FROM
        aka_title m
    JOIN
        cast_info c ON m.id = c.movie_id
    JOIN
        aka_name a ON a.person_id = c.person_id
    WHERE
        c.nr_order IS NOT NULL
),

MovieInfo AS (
    SELECT
        mi.movie_id,
        STRING_AGG(mi.info, ', ') AS info_aggregate
    FROM
        movie_info mi
    GROUP BY
        mi.movie_id
),

CompanyMovie AS (
    SELECT
        mc.movie_id,
        COALESCE(cn.name, 'Unknown Company') AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
    LEFT JOIN
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN
        company_type ct ON mc.company_type_id = ct.id
)

SELECT 
    mh.movie_id,
    mh.title,
    mh.production_year,
    mc.actor_name,
    mc.actor_rank,
    mi.info_aggregate,
    cm.company_name,
    cm.company_type
FROM 
    MovieHierarchy mh
LEFT JOIN 
    MovieCast mc ON mh.movie_id = mc.movie_id
LEFT JOIN 
    MovieInfo mi ON mh.movie_id = mi.movie_id
LEFT JOIN 
    CompanyMovie cm ON mh.movie_id = cm.movie_id
WHERE 
    mh.production_year >= 2000
    AND (mh.level > 0 OR mc.actor_name IS NOT NULL);
