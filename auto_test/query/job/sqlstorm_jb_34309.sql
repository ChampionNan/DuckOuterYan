
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        1 AS level,
        NULL AS parent_id
    FROM 
        aka_title m
    WHERE 
        m.episode_of_id IS NULL  

    UNION ALL

    SELECT 
        ep.id AS movie_id,
        ep.title,
        mh.level + 1,
        mh.movie_id AS parent_id
    FROM 
        aka_title ep
    JOIN 
        MovieHierarchy mh ON ep.episode_of_id = mh.movie_id
),
CastDetails AS (
    SELECT 
        ci.movie_id, 
        p.name AS person_name, 
        rt.role, 
        ci.nr_order,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_order
    FROM 
        cast_info ci
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
),
MovieKeywords AS (
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
    mh.movie_id,
    mh.title,
    mh.level,
    cd.person_name,
    cd.role,
    cd.role_order,
    mk.keywords,
    m.production_year 
FROM 
    MovieHierarchy mh
LEFT JOIN 
    CastDetails cd ON mh.movie_id = cd.movie_id
LEFT JOIN 
    aka_title m ON mh.movie_id = m.id
LEFT JOIN 
    MovieKeywords mk ON mh.movie_id = mk.movie_id
WHERE 
    m.production_year >= 2000
    AND (cd.role IN ('Director', 'Actor') OR cd.role IS NULL)
GROUP BY 
    mh.movie_id, mh.title, mh.level, cd.person_name, cd.role, cd.role_order, mk.keywords, m.production_year;
