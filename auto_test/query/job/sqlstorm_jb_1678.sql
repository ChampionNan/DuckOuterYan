WITH RankedMovies AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.production_year DESC) AS year_rank
    FROM 
        aka_title mt
    WHERE 
        mt.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
),
FilteredCasts AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        cp.role AS person_role,
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS cast_count
    FROM 
        cast_info ci
    JOIN 
        role_type cp ON ci.role_id = cp.id
    WHERE 
        ci.nr_order < 5
),
MovieInfo AS (
    SELECT 
        mi.movie_id,
        STRING_AGG(DISTINCT mi.info, '; ') AS movie_notes
    FROM 
        movie_info mi
    GROUP BY 
        mi.movie_id
)
SELECT 
    rm.title,
    rm.production_year,
    fc.person_role,
    COALESCE(fc.cast_count, 0) AS total_cast,
    mi.movie_notes
FROM 
    RankedMovies rm
LEFT JOIN 
    FilteredCasts fc ON rm.movie_id = fc.movie_id
LEFT JOIN 
    MovieInfo mi ON rm.movie_id = mi.movie_id
WHERE 
    rm.year_rank <= 10;
