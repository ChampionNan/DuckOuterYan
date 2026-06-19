WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
), 
ActorInfo AS (
    SELECT 
        a.id AS actor_id,
        a.name,
        c.movie_id,
        RANK() OVER (PARTITION BY a.id ORDER BY c.nr_order) AS role_rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    WHERE 
        c.nr_order IS NOT NULL
), 
MovieCompanies AS (
    SELECT 
        m.movie_id,
        COUNT(DISTINCT mc.company_id) AS company_count
    FROM 
        movie_companies mc
    JOIN 
        complete_cast m ON mc.movie_id = m.movie_id
    GROUP BY 
        m.movie_id
)

SELECT 
    rt.title AS Movie_Title,
    rt.production_year AS Production_Year,
    ai.name AS Actor_Name,
    ai.role_rank,
    COALESCE(mc.company_count, 0) AS Company_Count
FROM 
    RankedTitles rt
LEFT JOIN 
    ActorInfo ai ON rt.title_id = ai.movie_id
LEFT JOIN 
    MovieCompanies mc ON rt.title_id = mc.movie_id
WHERE 
    rt.rank < 5;
