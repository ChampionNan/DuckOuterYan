WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        1 AS depth
    FROM 
        aka_title mt
    WHERE 
        mt.production_year >= 2000

    UNION ALL

    SELECT 
        ml.linked_movie_id AS movie_id,
        at.title,
        at.production_year,
        mh.depth + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title at ON ml.linked_movie_id = at.id
    JOIN 
        MovieHierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.depth < 3  
),

FilteredCast AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS cast_count,
        ARRAY_AGG(DISTINCT an.name) AS actor_names
    FROM 
        cast_info ci
    LEFT JOIN 
        aka_name an ON ci.person_id = an.person_id
    WHERE 
        ci.person_role_id IS NOT NULL
    GROUP BY 
        ci.movie_id, ci.person_id
),

MovieDetails AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        fcast.cast_count,
        fcast.actor_names
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        FilteredCast fcast ON mh.movie_id = fcast.movie_id
)

SELECT 
    md.title,
    md.production_year,
    COALESCE(md.actor_names, ARRAY['No actors']) AS actor_names,
    md.cast_count,
    CASE 
        WHEN md.production_year < 2010 THEN 'Older Movie'
        WHEN md.production_year BETWEEN 2010 AND 2018 THEN 'Recent Movie'
        ELSE 'New Movie'
    END AS movie_category
FROM 
    MovieDetails md
LEFT JOIN 
    movie_info mi ON md.movie_id = mi.movie_id
WHERE 
    mi.info_type_id IS NOT NULL;
