
WITH RankedMovies AS (
    SELECT 
        a.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS RankYear
    FROM 
        aka_title AS a
    JOIN 
        title AS t ON a.movie_id = t.id
    WHERE 
        t.production_year IS NOT NULL
),
TopRankedMovies AS (
    SELECT 
        title, 
        production_year
    FROM 
        RankedMovies
    WHERE 
        RankYear <= 5
),
ActorsMovies AS (
    SELECT 
        n.name AS actor_name,
        t.title,
        t.production_year
    FROM 
        cast_info AS ci
    JOIN 
        aka_name AS n ON ci.person_id = n.person_id
    JOIN 
        aka_title AS a ON ci.movie_id = a.movie_id
    JOIN 
        title AS t ON a.movie_id = t.id
),
MoviesWithKeywords AS (
    SELECT 
        t.title,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM 
        title AS t
    JOIN 
        movie_keyword AS mk ON t.id = mk.movie_id
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    GROUP BY 
        t.title
)
SELECT 
    rm.title,
    rm.production_year,
    am.actor_name,
    mk.keywords
FROM 
    TopRankedMovies AS rm
LEFT JOIN 
    ActorsMovies AS am ON rm.title = am.title AND rm.production_year = am.production_year
LEFT JOIN 
    MoviesWithKeywords AS mk ON rm.title = mk.title
WHERE 
    am.actor_name IS NOT NULL OR mk.keywords IS NOT NULL;
