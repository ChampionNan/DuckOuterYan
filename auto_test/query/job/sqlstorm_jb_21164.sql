WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY t.id) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),

FilteredCast AS (
    SELECT 
        c.id AS cast_id,
        c.person_id,
        c.movie_id,
        coalesce(p.name, cn.name) AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_order
    FROM 
        cast_info c
    LEFT JOIN name p ON c.person_id = p.imdb_id
    LEFT JOIN char_name cn ON p.id = cn.imdb_id
),

MoviesWithKeywords AS (
    SELECT 
        m.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM 
        movie_keyword mk
    JOIN 
        aka_title m ON mk.movie_id = m.movie_id
    GROUP BY 
        m.movie_id
),

ComplexJoin AS (
    SELECT 
        DISTINCT r.movie_id,
        r.title,
        r.production_year,
        fc.actor_name,
        CASE 
            WHEN fc.actor_order IS NULL THEN 'Unassigned'
            ELSE CONCAT(fc.actor_name, ' (Order: ', fc.actor_order, ')')
        END AS detailed_actor_info,
        COALESCE(wk.keyword_count, 0) AS keyword_count
    FROM 
        RankedMovies r
    LEFT JOIN 
        FilteredCast fc ON r.movie_id = fc.movie_id
    LEFT JOIN 
        MoviesWithKeywords wk ON r.movie_id = wk.movie_id
    WHERE 
        r.year_rank <= 10
        AND (r.production_year > 2000 OR r.title LIKE '%The%')
)

SELECT 
    movie_id,
    title,
    production_year,
    detailed_actor_info,
    keyword_count
FROM 
    ComplexJoin;
