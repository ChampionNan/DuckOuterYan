
WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_by_year,
        COUNT(c.id) OVER (PARTITION BY t.id) AS cast_count
    FROM title t
    LEFT JOIN cast_info c ON t.id = c.movie_id
),
FilteredMovies AS (
    SELECT 
        rm.title_id,
        rm.title,
        rm.production_year,
        rm.rank_by_year,
        CASE 
            WHEN rm.cast_count = 0 THEN 'No Cast'
            WHEN rm.cast_count > 5 THEN 'Large Cast'
            ELSE 'Small Cast'
        END AS cast_size
    FROM RankedMovies rm
    WHERE rm.production_year >= 2000 AND rm.rank_by_year <= 10
),
FinalProfile AS (
    SELECT 
        fm.title_id,
        fm.title,
        fm.production_year,
        fm.cast_size,
        ak.name AS director_name
    FROM FilteredMovies fm
    LEFT JOIN complete_cast cc ON fm.title_id = cc.movie_id
    LEFT JOIN aka_name ak ON cc.subject_id = ak.person_id AND ak.name LIKE '%Director%'
)
SELECT 
    fp.title_id,
    fp.title,
    fp.production_year,
    fp.cast_size,
    COALESCE(fp.director_name, 'Unknown Director') AS director_name,
    CASE 
        WHEN fp.production_year = EXTRACT(YEAR FROM DATE '2024-10-01') THEN 'New Release'
        WHEN fp.production_year = EXTRACT(YEAR FROM DATE '2024-10-01') - 1 THEN 'Last Year Release'
        ELSE 'Older Release'
    END AS release_status
FROM FinalProfile fp
WHERE (fp.cast_size = 'Large Cast' AND fp.production_year = 2023)
   OR (CASE 
            WHEN fp.production_year = EXTRACT(YEAR FROM DATE '2024-10-01') THEN 'New Release'
            WHEN fp.production_year = EXTRACT(YEAR FROM DATE '2024-10-01') - 1 THEN 'Last Year Release'
            ELSE 'Older Release'
        END = 'Older Release' AND fp.director_name IS NULL);
