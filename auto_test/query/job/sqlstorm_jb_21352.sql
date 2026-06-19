
WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        AVG(ci.nr_order) OVER (PARTITION BY t.id) AS avg_order
    FROM 
        aka_title t
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id 
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id 
    WHERE 
        t.production_year IS NOT NULL
),
GenreCounts AS (
    SELECT 
        t.id AS title_id,
        COUNT(DISTINCT k.id) AS num_genres
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id 
    JOIN 
        keyword k ON mk.keyword_id = k.id 
    GROUP BY 
        t.id
),
CombinedResults AS (
    SELECT 
        rm.title,
        rm.production_year,
        rm.title_rank,
        gc.num_genres,
        CASE 
            WHEN rm.avg_order IS NULL THEN 'No Cast' 
            ELSE CAST(rm.avg_order AS VARCHAR)
        END AS avg_cast_order
    FROM 
        RankedMovies rm
    LEFT JOIN 
        GenreCounts gc ON rm.title_id = gc.title_id
)
SELECT 
    title,
    production_year,
    title_rank,
    num_genres,
    CASE 
        WHEN num_genres > 3 THEN 'Diverse Genre'
        WHEN title_rank = 1 AND num_genres IS NOT NULL THEN 'Top Movie of Year'
        ELSE 'Regular Movie'
    END AS classification
FROM 
    CombinedResults
WHERE 
    (num_genres IS NOT NULL AND num_genres < 5) 
    OR (avg_cast_order IS NOT NULL AND avg_cast_order = 'No Cast');
