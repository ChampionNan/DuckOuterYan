
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(c.person_id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        cast_info c ON t.movie_id = c.movie_id
    GROUP BY 
        t.id, t.title, t.production_year
),
FilteredMovies AS (
    SELECT 
        rm.movie_id, 
        rm.title,
        rm.production_year,
        rm.cast_count,
        CASE 
            WHEN rm.title_rank IS NULL THEN 'Unknown Rank'
            ELSE 'Rank ' || CAST(rm.title_rank AS TEXT) 
        END AS title_status
    FROM 
        RankedMovies rm
    WHERE 
        rm.cast_count > 5
),
Keywords AS (
    SELECT 
        mk.movie_id,
        k.keyword
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword LIKE 'Drama%'
),
FinalResults AS (
    SELECT 
        fm.title,
        fm.production_year,
        fm.cast_count,
        COALESCE(kw.keyword, 'No Keywords') AS keyword_info,
        CASE 
            WHEN fm.cast_count IS NULL THEN 'No Cast Info'
            ELSE 'Cast Count Exists'
        END AS cast_info_status
    FROM 
        FilteredMovies fm
    LEFT JOIN 
        Keywords kw ON fm.movie_id = kw.movie_id
)
SELECT 
    fr.title,
    fr.production_year,
    fr.cast_count,
    fr.keyword_info,
    fr.cast_info_status,
    CASE 
        WHEN fr.cast_count IS NOT NULL AND fr.keyword_info <> 'No Keywords' THEN 'Qualified Movie'
        ELSE 'Needs More Info'
    END AS movie_qualification
FROM 
    FinalResults fr
WHERE 
    fr.production_year >= 2000;
