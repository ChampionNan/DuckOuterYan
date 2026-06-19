WITH ranked_titles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
), 
company_movies AS (
    SELECT 
        mc.movie_id, 
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
), 
actor_roles AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name, 
        r.role AS role_name,
        COUNT(*) AS role_count
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type r ON ci.role_id = r.id
    GROUP BY 
        ci.movie_id, a.name, r.role
)
SELECT 
    tt.title,
    tt.production_year,
    cm.company_name,
    cm.company_type,
    ar.actor_name,
    ar.role_name,
    ar.role_count,
    CASE 
        WHEN ar.role_count IS NULL THEN 'No Roles Assigned'
        ELSE 'Roles Present'
    END AS role_assignment_status
FROM 
    ranked_titles tt
LEFT JOIN 
    company_movies cm ON tt.title_id = cm.movie_id
LEFT JOIN 
    actor_roles ar ON tt.title_id = ar.movie_id 
WHERE 
    tt.title_rank <= 5;
