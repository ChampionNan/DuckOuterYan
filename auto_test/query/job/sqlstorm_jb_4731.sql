
WITH movie_details AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        COALESCE(GROUP_CONCAT(DISTINCT cn.name), 'No Companies') AS company_names
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_companies mc ON mt.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        mt.production_year >= 2000
    GROUP BY 
        mt.id, mt.title, mt.production_year
),
person_roles AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        rt.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_order
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        a.name IS NOT NULL
),
ranked_movies AS (
    SELECT 
        md.movie_id,
        md.title,
        md.production_year,
        pr.actor_name,
        pr.role_name,
        pr.role_order
    FROM 
        movie_details md
    LEFT JOIN 
        person_roles pr ON md.movie_id = pr.movie_id
)
SELECT 
    rm.title,
    rm.production_year,
    rm.actor_name,
    rm.role_name,
    COUNT(rm.role_name) OVER (PARTITION BY rm.movie_id) AS total_roles,
    CASE 
        WHEN rm.role_order IS NULL THEN 'No Role'
        ELSE rm.role_name
    END AS final_role_name
FROM 
    ranked_movies rm
WHERE 
    rm.production_year IS NOT NULL 
    AND rm.actor_name IS NOT NULL;
