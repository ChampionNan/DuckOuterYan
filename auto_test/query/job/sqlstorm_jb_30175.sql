WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        1 AS level
    FROM 
        aka_title m
    WHERE 
        m.episode_of_id IS NULL
    
    UNION ALL
    
    SELECT 
        e.id AS movie_id,
        e.title,
        e.production_year,
        mh.level + 1
    FROM 
        aka_title e
    INNER JOIN 
        MovieHierarchy mh ON e.episode_of_id = mh.movie_id
),
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        RANK() OVER (PARTITION BY mh.production_year ORDER BY mh.level) AS movie_rank
    FROM 
        MovieHierarchy mh
),
CastDetails AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        a.md5sum,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS role_number
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieKeywordDetails AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    COALESCE(k.keywords, 'No Keywords') AS keywords,
    COALESCE(cd.actor_name, 'No Cast') AS actor_name,
    COALESCE(cd.role, 'None') AS role,
    COALESCE(cd.role_number, 0) AS role_position
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    MovieKeywordDetails k ON rm.movie_id = k.movie_id
WHERE 
    rm.production_year >= 2000;
