
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        title.id AS movie_id,
        title.title,
        title.production_year,
        1 AS depth,
        title.episode_of_id
    FROM 
        title
    WHERE 
        title.episode_of_id IS NULL

    UNION ALL

    SELECT 
        t.id,
        t.title,
        t.production_year,
        mh.depth + 1,
        t.episode_of_id
    FROM 
        title t
    JOIN 
        MovieHierarchy mh ON t.episode_of_id = mh.movie_id
),
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        mh.depth,
        RANK() OVER (PARTITION BY mh.depth ORDER BY mh.production_year DESC) AS production_rank
    FROM 
        MovieHierarchy mh
),
Companies AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY cn.name) AS company_rank
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        STRING_AGG(aka.name, ', ') AS cast_names
    FROM 
        cast_info ci
    JOIN 
        aka_name aka ON ci.person_id = aka.person_id
    GROUP BY 
        ci.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.depth,
    rm.production_rank,
    c.company_name,
    c.company_type,
    cd.cast_names
FROM 
    RankedMovies rm
LEFT JOIN 
    Companies c ON rm.movie_id = c.movie_id AND c.company_rank = 1
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
WHERE 
    rm.production_year >= 2000
    AND (c.company_type IS NOT NULL OR cd.cast_names IS NOT NULL);
