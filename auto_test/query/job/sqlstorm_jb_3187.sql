
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rn
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        a.person_id,
        a.name,
        c.movie_id,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY c.nr_order) AS role_rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
MovieCompanies AS (
    SELECT 
        cc.movie_id,
        COUNT(DISTINCT mc.company_id) AS company_count
    FROM 
        movie_companies mc
    JOIN 
        complete_cast cc ON mc.movie_id = cc.movie_id
    GROUP BY 
        cc.movie_id
)

SELECT 
    rt.title,
    rt.production_year,
    ar.name AS actor_name,
    ar.role,
    COALESCE(mc.company_count, 0) AS total_companies,
    CASE 
        WHEN ar.role_rank = 1 THEN 'Lead'
        WHEN ar.role_rank <= 3 THEN 'Supporting'
        ELSE 'Background'
    END AS role_type
FROM 
    RankedTitles rt
LEFT JOIN 
    ActorRoles ar ON rt.title_id = ar.movie_id AND ar.role_rank <= 3
LEFT JOIN 
    MovieCompanies mc ON rt.title_id = mc.movie_id
WHERE 
    rt.rn <= 5;
