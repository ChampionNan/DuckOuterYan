WITH ranked_movies AS (
    SELECT 
        a.title,
        a.production_year,
        RANK() OVER (PARTITION BY a.production_year ORDER BY m.info DESC) AS rank
    FROM 
        aka_title a
    JOIN 
        movie_info m ON a.id = m.movie_id
    WHERE 
        m.info_type_id = (SELECT id FROM info_type WHERE info = 'Budget')
        AND m.info IS NOT NULL
),
genre_count AS (
    SELECT 
        a.id AS movie_id,
        COUNT(k.id) AS keyword_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        a.production_year > 2000
    GROUP BY 
        a.id
)
SELECT 
    r.title,
    r.production_year,
    COALESCE(gc.keyword_count, 0) AS keyword_count,
    CASE 
        WHEN r.rank <= 10 THEN 'Top 10' 
        ELSE 'Other' 
    END AS rank_category
FROM 
    ranked_movies r
LEFT JOIN 
    genre_count gc ON r.title = (SELECT title FROM aka_title WHERE id = gc.movie_id)
WHERE 
    r.rank <= 20;
