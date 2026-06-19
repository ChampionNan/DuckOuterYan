WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie') 
        AND t.production_year IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year, 
        rm.keyword 
    FROM 
        RankedMovies rm
    WHERE 
        rm.year_rank <= 10  
),
MovieDetails AS (
    SELECT 
        fm.*, 
        COALESCE(ci.person_role_id, 0) AS person_role_id,
        COUNT(ci.id) AS cast_count
    FROM 
        FilteredMovies fm
    LEFT JOIN 
        complete_cast cc ON fm.movie_id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.id 
    GROUP BY 
        fm.movie_id, fm.title, fm.production_year, fm.keyword, ci.person_role_id
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    md.keyword,
    md.cast_count
FROM 
    MovieDetails md
WHERE 
    md.cast_count > 5;
