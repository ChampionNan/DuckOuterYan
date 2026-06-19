
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM title t
    WHERE t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        a.id AS actor_id,
        a.name,
        c.movie_id,
        r.role AS actor_role
    FROM aka_name a
    JOIN cast_info c ON a.person_id = c.person_id
    JOIN role_type r ON c.role_id = r.id
),
CompanyTitles AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(DISTINCT cn.name, ', ') AS companies
    FROM movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    GROUP BY mc.movie_id
)
SELECT 
    rt.title AS Title,
    rt.production_year AS Production_Year,
    ar.name AS Actor_Name,
    ar.actor_role AS Role,
    ct.companies AS Production_Companies
FROM RankedTitles rt
LEFT JOIN ActorRoles ar ON rt.title_id = ar.movie_id
LEFT JOIN CompanyTitles ct ON rt.title_id = ct.movie_id
WHERE rt.rn <= 5 AND (ar.actor_role IS NULL OR ar.actor_role != 'Director');
