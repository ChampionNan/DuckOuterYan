WITH RECURSIVE MovieHierarchy AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        1 AS level
    FROM
        aka_title t
    WHERE
        t.production_year >= 2000
    
    UNION ALL
    
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        mh.level + 1
    FROM
        MovieHierarchy mh
    JOIN
        movie_link ml ON mh.movie_id = ml.movie_id
    JOIN
        aka_title t ON ml.linked_movie_id = t.id
    WHERE
        mh.level < 3 
),

RankedMovies AS (
    SELECT
        mh.movie_id,
        mh.title,
        mh.production_year,
        ROW_NUMBER() OVER (PARTITION BY mh.production_year ORDER BY mh.production_year DESC) AS year_rank
    FROM
        MovieHierarchy mh
),

CastDetails AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        ci.nr_order
    FROM
        cast_info ci
    JOIN
        aka_name ak ON ci.person_id = ak.person_id
    WHERE
        ak.name IS NOT NULL
),

CompanyDetails AS (
    SELECT
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
    JOIN
        company_name cn ON mc.company_id = cn.imdb_id
    JOIN
        company_type ct ON mc.company_type_id = ct.id
)

SELECT
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.year_rank,
    c.actor_name,
    c.nr_order,
    COALESCE(cd.company_name, 'Independent') AS company_name,
    COALESCE(cd.company_type, 'Unknown') AS company_type
FROM
    RankedMovies rm
LEFT JOIN
    CastDetails c ON rm.movie_id = c.movie_id
LEFT JOIN
    CompanyDetails cd ON rm.movie_id = cd.movie_id
WHERE
    rm.year_rank <= 5;
