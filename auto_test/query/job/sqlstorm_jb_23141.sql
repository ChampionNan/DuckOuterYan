WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        a.id AS movie_id,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank,
        COUNT(mk.movie_id) OVER (PARTITION BY a.id) AS keyword_count,
        AVG(COALESCE(ki.info_type_id, 0)) OVER (PARTITION BY a.id) AS avg_info_type_id
    FROM 
        aka_title a
        LEFT JOIN movie_keyword mk ON a.id = mk.movie_id
        LEFT JOIN movie_info mi ON a.id = mi.movie_id
        LEFT JOIN movie_info_idx ki ON a.id = ki.movie_id
    WHERE 
        a.production_year IS NOT NULL
        AND a.kind_id IN (SELECT id FROM kind_type WHERE kind = 'feature')
),
MoviesWithNames AS (
    SELECT 
        rm.title,
        rm.production_year,
        ak.name AS actor_name,
        rm.keyword_count,
        rm.avg_info_type_id
    FROM 
        RankedMovies rm
        JOIN cast_info ci ON rm.movie_id = ci.movie_id
        LEFT JOIN aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        ak.name IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        mw.title,
        mw.production_year,
        mw.actor_name,
        mw.keyword_count,
        mw.avg_info_type_id,
        CASE 
            WHEN mw.keyword_count > 5 THEN 'High'
            WHEN mw.keyword_count BETWEEN 3 AND 5 THEN 'Moderate'
            ELSE 'Low'
        END AS keyword_intensity
    FROM 
        MoviesWithNames mw
    WHERE 
        mw.production_year > 2000
        AND mw.avg_info_type_id IS NOT NULL
)
SELECT 
    f.title,
    f.production_year,
    f.actor_name,
    f.keyword_count,
    f.keyword_intensity,
    CASE 
        WHEN f.keyword_intensity = 'High' THEN 'Top-rated'
        ELSE 'Standard'
    END AS movie_category
FROM 
    FilteredMovies f
LEFT JOIN title t ON f.title = t.title
WHERE 
    t.imdb_id IS NULL;
