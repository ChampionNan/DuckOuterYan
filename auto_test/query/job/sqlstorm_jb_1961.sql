WITH ranked_movies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC, t.title ASC) AS rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),

cast_details AS (
    SELECT 
        c.movie_id,
        c.person_id,
        c.note,
        p.name AS actor_name,
        COALESCE(r.role, 'Unknown') AS role
    FROM 
        cast_info c
    LEFT JOIN 
        role_type r ON c.role_id = r.id
    INNER JOIN 
        aka_name p ON p.person_id = c.person_id
),

movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    INNER JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)

SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    cd.actor_name,
    cd.role,
    mk.keywords,
    CASE 
        WHEN cd.note IS NOT NULL THEN cd.note
        ELSE 'No Notes Available' 
    END AS notes
FROM 
    ranked_movies rm
LEFT JOIN 
    cast_details cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    movie_keywords mk ON rm.movie_id = mk.movie_id
WHERE 
    rm.rank <= 5;
