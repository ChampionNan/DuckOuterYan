WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        tk.keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY tk.keyword) as rn
    FROM 
        aka_title AS m
    JOIN 
        movie_keyword AS mk ON m.id = mk.movie_id
    JOIN 
        keyword AS tk ON mk.keyword_id = tk.id
    WHERE 
        m.production_year >= 2000 
        AND m.production_year <= 2023
),
TopKeywords AS (
    SELECT 
        movie_id,
        STRING_AGG(keyword, ', ') AS keywords
    FROM 
        RankedMovies
    WHERE 
        rn <= 3
    GROUP BY 
        movie_id
),
CastInfo AS (
    SELECT 
        c.id AS cast_id,
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name
    FROM 
        cast_info AS c
    JOIN 
        aka_name AS a ON c.person_id = a.person_id
    JOIN 
        role_type AS r ON c.role_id = r.id
)
SELECT 
    m.title AS Movie_Title,
    m.production_year AS Production_Year,
    k.keywords AS Top_Keywords,
    c.actor_name AS Actor,
    c.role_name AS Role
FROM 
    aka_title AS m
LEFT JOIN 
    TopKeywords AS k ON m.id = k.movie_id
LEFT JOIN 
    CastInfo AS c ON m.id = c.movie_id
WHERE 
    c.role_name IS NOT NULL;
