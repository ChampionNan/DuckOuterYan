
WITH RankedMovies AS (
    SELECT 
        t.title,
        t.production_year,
        COUNT(ci.person_id) AS actor_count
    FROM 
        title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN 
        name n ON ak.person_id = n.imdb_id
    GROUP BY 
        t.title, t.production_year
),
TopMovies AS (
    SELECT 
        title, 
        production_year, 
        actor_count,
        ROW_NUMBER() OVER (ORDER BY actor_count DESC) AS rn
    FROM 
        RankedMovies
)
SELECT 
    tm.title,
    tm.production_year,
    tm.actor_count,
    cn.name AS company_name,
    ci.note AS role_note
FROM 
    TopMovies tm
JOIN 
    movie_companies mc ON tm.title = (SELECT title FROM title WHERE id = mc.movie_id)
JOIN 
    company_name cn ON mc.company_id = cn.id
JOIN 
    complete_cast cc ON mc.movie_id = cc.movie_id
JOIN 
    cast_info ci ON cc.subject_id = ci.person_id
WHERE 
    tm.rn <= 10;
