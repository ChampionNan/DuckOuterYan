WITH ranked_movies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY COUNT(DISTINCT ci.person_id) DESC) AS rank
    FROM 
        title t 
    JOIN 
        complete_cast cc ON t.id = cc.movie_id 
    JOIN 
        cast_info ci ON cc.subject_id = ci.id 
    GROUP BY 
        t.id, t.title, t.production_year
),
top_movies AS (
    SELECT 
        movie_id, title, production_year 
    FROM 
        ranked_movies 
    WHERE 
        rank <= 5
)
SELECT 
    tm.title,
    tm.production_year,
    n.name AS actor_name,
    c.name AS company_name,
    k.keyword
FROM 
    top_movies tm 
JOIN 
    complete_cast cc ON tm.movie_id = cc.movie_id 
JOIN 
    cast_info ci ON cc.subject_id = ci.id 
JOIN 
    aka_name an ON ci.person_id = an.person_id 
JOIN 
    name n ON an.person_id = n.imdb_id 
LEFT JOIN 
    movie_companies mc ON tm.movie_id = mc.movie_id 
LEFT JOIN 
    company_name c ON mc.company_id = c.id 
LEFT JOIN 
    movie_keyword mk ON tm.movie_id = mk.movie_id 
LEFT JOIN 
    keyword k ON mk.keyword_id = k.id;
