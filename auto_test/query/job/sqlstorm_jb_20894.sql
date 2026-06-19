
WITH ranked_movies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
movie_cast AS (
    SELECT 
        m.title_id,
        c.person_id,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY m.title_id ORDER BY c.nr_order) AS role_order
    FROM 
        ranked_movies m
    JOIN 
        cast_info c ON m.title_id = c.movie_id 
    LEFT JOIN 
        role_type r ON c.role_id = r.id
),
movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
movies_with_cast AS (
    SELECT 
        m.title_id,
        m.title,
        m.production_year,
        COALESCE(c.person_id, -1) AS person_id,  
        COALESCE(c.role, 'Unknown') AS role,
        CASE 
            WHEN m.production_year < 2000 THEN 'Classic'
            WHEN m.production_year BETWEEN 2000 AND 2010 THEN 'Modern'
            ELSE 'Recent'
        END AS era
    FROM 
        ranked_movies m
    LEFT JOIN 
        movie_cast c ON m.title_id = c.title_id AND c.role_order = 1
),
final_movie_data AS (
    SELECT 
        mwc.title,
        mwc.production_year,
        mwc.person_id,
        mwc.role,
        mwc.era,
        COALESCE(mk.keywords, 'No Keywords') AS keywords
    FROM 
        movies_with_cast mwc
    LEFT JOIN 
        movie_keywords mk ON mwc.title_id = mk.movie_id
)

SELECT 
    f.title,
    f.production_year,
    f.role,
    f.era,
    CASE 
        WHEN f.role = 'Unknown' THEN 'Not Cast'
        ELSE 'Cast'
    END AS casting_status,
    LAG(f.role) OVER (PARTITION BY f.production_year ORDER BY f.title) AS previous_role,
    COUNT(*) OVER (PARTITION BY f.era) AS total_movies_in_era,
    SUM(CASE WHEN f.role IS NOT NULL THEN 1 ELSE 0 END) OVER () AS total_casted_roles
FROM 
    final_movie_data f
WHERE 
    f.production_year IS NOT NULL AND f.production_year > 1990;
