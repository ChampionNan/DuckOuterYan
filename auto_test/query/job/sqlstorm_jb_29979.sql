WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        ak.name AS actor_name,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS movie_rank,
        COUNT(DISTINCT c.id) AS cast_count
    FROM 
        aka_title a
    JOIN 
        cast_info c ON a.id = c.movie_id
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year >= 2000
    GROUP BY 
        a.id, a.title, a.production_year, ak.name, k.keyword
),
FilteredMovies AS (
    SELECT 
        rm.title, 
        rm.production_year, 
        rm.actor_name,
        rm.keyword,
        rm.cast_count
    FROM 
        RankedMovies rm
    WHERE 
        rm.cast_count > 5 AND rm.movie_rank = 1
)
SELECT 
    fm.title,
    fm.production_year,
    fm.actor_name,
    fm.keyword,
    COUNT(*) OVER (PARTITION BY fm.keyword) AS keyword_count
FROM 
    FilteredMovies fm;
