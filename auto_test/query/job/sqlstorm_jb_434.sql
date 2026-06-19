
WITH title_info AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        COUNT(DISTINCT k.id) AS keyword_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        t.id, t.title, t.production_year
),
cast_details AS (
    SELECT 
        c.movie_id,
        c.person_id,
        p.name AS actor_name,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_order
    FROM 
        cast_info c
    JOIN 
        aka_name p ON c.person_id = p.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
movies_with_cast AS (
    SELECT 
        ti.title,
        ti.production_year,
        cd.actor_name,
        cd.role_name,
        ti.keyword_count
    FROM 
        title_info ti
    LEFT JOIN 
        cast_details cd ON ti.title_id = cd.movie_id
)
SELECT 
    mwc.title,
    mwc.production_year,
    COALESCE(mwc.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(mwc.role_name, 'Unknown Role') AS role_name,
    mwc.keyword_count,
    CASE 
        WHEN mwc.keyword_count > 5 THEN 'Popular'
        ELSE 'Less Popular'
    END AS popularity_category
FROM 
    movies_with_cast mwc
WHERE 
    mwc.production_year IS NOT NULL;
