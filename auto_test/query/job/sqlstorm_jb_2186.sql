WITH movie_years AS (
    SELECT 
        title.id AS movie_id,
        title.production_year,
        COUNT(DISTINCT cast_info.person_id) AS cast_count
    FROM 
        title
    LEFT JOIN 
        cast_info ON title.id = cast_info.movie_id
    GROUP BY 
        title.id, title.production_year
),
top_movies AS (
    SELECT 
        movie_id,
        production_year,
        cast_count,
        RANK() OVER (PARTITION BY production_year ORDER BY cast_count DESC) AS rank
    FROM 
        movie_years
),
movie_details AS (
    SELECT 
        tm.movie_id,
        t.title,
        c.name AS company_name,
        tm.production_year
    FROM 
        top_movies tm
    JOIN 
        title t ON tm.movie_id = t.id
    LEFT JOIN 
        movie_companies mc ON tm.movie_id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    WHERE 
        tm.rank <= 5
)
SELECT 
    md.title,
    md.production_year,
    COALESCE(md.company_name, 'No Company') AS company_name,
    tm.cast_count
FROM 
    movie_details md
JOIN 
    top_movies tm ON md.movie_id = tm.movie_id
WHERE 
    md.production_year BETWEEN 1990 AND 2000;
