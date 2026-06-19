
WITH RecursiveActorMovies AS (
    SELECT 
        a.id AS actor_id, 
        a.person_id,
        a.name,
        ct.kind AS company_type,
        at.title AS movie_title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY at.production_year DESC) AS movie_rank
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        aka_title at ON ci.movie_id = at.id
    LEFT JOIN 
        movie_companies mc ON at.id = mc.movie_id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        a.name IS NOT NULL
),
ActorAwards AS (
    SELECT 
        p.person_id,
        COUNT(DISTINCT mi.id) AS award_count
    FROM 
        person_info p
    JOIN 
        movie_info mi ON p.person_id = mi.movie_id
    JOIN 
        title t ON mi.movie_id = t.id
    WHERE 
        mi.info_type_id = (SELECT id FROM info_type WHERE info = 'award' LIMIT 1)
    GROUP BY 
        p.person_id
)
SELECT 
    ram.actor_id, 
    ram.name, 
    ram.movie_title, 
    ram.production_year, 
    COALESCE(aa.award_count, 0) AS total_awards,
    CASE 
        WHEN ram.movie_rank = 1 AND COALESCE(aa.award_count, 0) > 0 THEN 'Leading Actor with Awards'
        WHEN ram.movie_rank = 1 AND COALESCE(aa.award_count, 0) = 0 THEN 'Leading Actor without Awards'
        WHEN ram.movie_rank > 1 THEN 'Supporting Actor'
    END AS actor_status
FROM 
    RecursiveActorMovies ram
LEFT JOIN 
    ActorAwards aa ON ram.person_id = aa.person_id
WHERE 
    ram.production_year >= 2000
    AND ram.company_type LIKE 'Production%'
    AND (ram.movie_title IS NOT NULL OR ram.movie_rank < 5);
