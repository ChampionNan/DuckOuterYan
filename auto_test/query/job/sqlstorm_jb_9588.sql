WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id, 
        t.title, 
        t.production_year, 
        COUNT(DISTINCT ci.person_id) AS actor_count
    FROM 
        aka_title t
    JOIN 
        movie_companies mc ON mc.movie_id = t.id
    JOIN 
        company_name cn ON cn.id = mc.company_id
    LEFT JOIN 
        complete_cast cc ON cc.movie_id = t.id
    LEFT JOIN 
        cast_info ci ON ci.movie_id = t.id
    GROUP BY 
        t.id, t.title, t.production_year
), 
TopMovies AS (
    SELECT 
        movie_id, 
        title, 
        production_year, 
        actor_count,
        ROW_NUMBER() OVER (ORDER BY actor_count DESC) AS rank
    FROM 
        RankedMovies
    WHERE 
        production_year > 2000
)
SELECT 
    tm.title, 
    tm.production_year, 
    tm.actor_count, 
    cn.name AS company_name
FROM 
    TopMovies tm
JOIN 
    movie_companies mc ON mc.movie_id = tm.movie_id
JOIN 
    company_name cn ON cn.id = mc.company_id
WHERE 
    tm.rank <= 10;
