WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year, 
        0 AS level
    FROM 
        aka_title m
    WHERE 
        m.episode_of_id IS NULL 
    UNION ALL
    SELECT 
        e.id AS movie_id, 
        e.title, 
        e.production_year, 
        h.level + 1
    FROM 
        aka_title e
    INNER JOIN 
        MovieHierarchy h ON e.episode_of_id = h.movie_id 
),
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        ROW_NUMBER() OVER (PARTITION BY mh.production_year ORDER BY mh.title) AS rn,
        COUNT(*) OVER (PARTITION BY mh.production_year) AS total_movies
    FROM 
        MovieHierarchy mh
),
CastDetails AS (
    SELECT 
        c.movie_id, 
        p.name AS person_name,
        c.nr_order,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS role_rank
    FROM 
        cast_info c
    JOIN 
        aka_name p ON c.person_id = p.person_id
),
MovieKeywords AS (
    SELECT 
        m.movie_id, 
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword m
    JOIN 
        keyword k ON m.keyword_id = k.id
    GROUP BY 
        m.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    cd.person_name,
    cd.nr_order AS cast_order,
    mk.keywords,
    CASE 
        WHEN rm.rn = 1 THEN 'First Movie of the Year'
        WHEN rm.rn = total_movies THEN 'Last Movie of the Year'
        ELSE 'Middle Movie of the Year'
    END AS position_description
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    mk.keywords IS NOT NULL OR cd.person_name IS NOT NULL;
