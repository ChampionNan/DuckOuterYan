
WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
cast_with_names AS (
    SELECT 
        c.movie_id,
        c.person_id,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
movies_with_info AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ki.kind AS genre,
        STRING_AGG(DISTINCT k.keyword, ',' ORDER BY k.keyword) AS keywords
    FROM 
        title m
    LEFT JOIN 
        kind_type ki ON m.kind_id = ki.id
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        m.id, m.title, m.production_year, ki.kind
)
SELECT 
    r.title_id,
    r.title,
    r.production_year,
    r.title_rank,
    c.actor_name,
    c.role_name,
    m.keywords,
    m.genre
FROM 
    ranked_titles r
JOIN 
    movies_with_info m ON r.title_id = m.movie_id
LEFT JOIN 
    cast_with_names c ON m.movie_id = c.movie_id
WHERE 
    r.title_rank <= 5;
