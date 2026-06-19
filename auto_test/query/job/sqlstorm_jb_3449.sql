WITH RankedMovies AS (
    SELECT 
        a.title,
        ca.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY c.nr_order) AS actor_rank,
        a.production_year,
        COUNT(DISTINCT k.keyword) AS keyword_count
    FROM 
        aka_title a
    JOIN 
        cast_info c ON a.id = c.movie_id
    JOIN 
        aka_name ca ON c.person_id = ca.person_id
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year IS NOT NULL AND
        ca.name IS NOT NULL 
    GROUP BY 
        a.id, a.title, ca.name, a.production_year, c.nr_order
),
FilteredMovies AS (
    SELECT 
        *,
        MAX(production_year) OVER (PARTITION BY actor_name) AS latest_movie_year
    FROM 
        RankedMovies
)
SELECT 
    f.title,
    f.actor_name,
    f.actor_rank,
    f.production_year,
    f.keyword_count,
    CASE 
        WHEN f.production_year = f.latest_movie_year THEN 'Latest'
        ELSE 'Older'
    END AS movie_status
FROM 
    FilteredMovies f
WHERE 
    f.actor_rank <= 3;
