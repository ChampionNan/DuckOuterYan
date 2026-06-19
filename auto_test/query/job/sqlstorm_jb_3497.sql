WITH ranked_titles AS (
    SELECT 
        a.id AS aka_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        aka_title t ON c.movie_id = t.movie_id
    WHERE 
        t.production_year >= 2000
),
genre_titles AS (
    SELECT 
        m.movie_id,
        STRING_AGG(g.keyword, ', ') AS genres
    FROM 
        movie_keyword m
    JOIN 
        keyword g ON m.keyword_id = g.id
    GROUP BY 
        m.movie_id
)
SELECT 
    a.name,
    r.title,
    r.production_year,
    g.genres,
    CASE 
        WHEN r.production_year IS NULL THEN 'Unknown Year'
        ELSE CAST(r.production_year AS TEXT)
    END AS year_label
FROM 
    ranked_titles r
LEFT JOIN 
    aka_name a ON r.aka_id = a.id
LEFT JOIN 
    genre_titles g ON r.aka_id = g.movie_id
WHERE 
    r.rank = 1;
