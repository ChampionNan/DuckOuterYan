WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_title,
        COUNT(DISTINCT ci.person_id) AS total_cast
    FROM 
        aka_title t
        LEFT JOIN cast_info ci ON t.movie_id = ci.movie_id
    WHERE 
        t.production_year IS NOT NULL
    GROUP BY 
        t.id, t.title, t.production_year
),
FilteredMovies AS (
    SELECT 
        rm.*,
        CASE 
            WHEN rm.total_cast > 10 THEN 'Large Cast'
            WHEN rm.total_cast BETWEEN 5 AND 10 THEN 'Medium Cast'
            ELSE 'Small Cast'
        END AS cast_size
    FROM 
        RankedMovies rm
    WHERE 
        rm.rank_title <= 5 AND rm.production_year > 2000
)
SELECT 
    fm.title,
    fm.production_year,
    fm.cast_size,
    ak.name AS actor_name,
    ki.keyword AS movie_keyword
FROM 
    FilteredMovies fm
    LEFT JOIN cast_info ci ON fm.movie_id = ci.movie_id
    LEFT JOIN aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN movie_keyword mk ON fm.movie_id = mk.movie_id
    LEFT JOIN keyword ki ON mk.keyword_id = ki.id
WHERE 
    ak.name IS NOT NULL;
