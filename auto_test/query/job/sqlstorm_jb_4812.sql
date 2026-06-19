WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
actor_roles AS (
    SELECT 
        ca.movie_id,
        c.name AS actor_name,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ca.movie_id ORDER BY ca.nr_order) AS role_order
    FROM 
        cast_info ca
    JOIN 
        aka_name c ON ca.person_id = c.person_id
    JOIN 
        role_type r ON ca.role_id = r.id
),
movie_keywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rt.production_year,
    rt.title,
    ar.actor_name,
    ar.role_name,
    mk.keywords
FROM 
    ranked_titles rt
LEFT JOIN 
    actor_roles ar ON rt.title_id = ar.movie_id AND ar.role_order = 1
LEFT JOIN 
    movie_keywords mk ON rt.title_id = mk.movie_id
WHERE 
    rt.rank <= 5;
