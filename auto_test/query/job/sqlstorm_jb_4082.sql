WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.imdb_index) AS movie_rank
    FROM 
        aka_title a
    WHERE 
        a.production_year IS NOT NULL
),
TopCast AS (
    SELECT 
        c.movie_id,
        ak.name AS actor_name,
        RANK() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name ak ON c.person_id = ak.person_id
    WHERE 
        ak.name IS NOT NULL
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords_list
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    COALESCE(tc.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(mk.keywords_list, 'No Keywords') AS keywords,
    CASE 
        WHEN rm.movie_rank <= 5 THEN 'Top 5 Movies'
        ELSE 'Other Movies'
    END AS movie_category
FROM 
    RankedMovies rm
LEFT JOIN 
    TopCast tc ON rm.movie_id = tc.movie_id AND tc.actor_rank <= 3
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    rm.movie_rank <= 10;
