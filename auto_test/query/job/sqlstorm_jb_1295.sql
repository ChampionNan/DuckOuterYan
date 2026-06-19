
WITH RankedTitles AS (
    SELECT 
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.id) AS title_rank,
        COALESCE(k.keyword, 'No Keyword') AS keyword,
        a.id
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
), 
ActorCount AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
), 
MoviesWithDetails AS (
    SELECT 
        t.title,
        t.production_year,
        ac.actor_count,
        COALESCE(cn.name, 'Unknown Company') AS company_name
    FROM 
        RankedTitles t
    LEFT JOIN 
        ActorCount ac ON t.id = ac.movie_id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
)
SELECT 
    m.title,
    m.production_year,
    m.actor_count,
    m.company_name,
    CASE 
        WHEN m.actor_count IS NULL THEN 'No Actors'
        WHEN m.actor_count < 5 THEN 'Few Actors'
        ELSE 'Many Actors'
    END AS actor_category
FROM 
    MoviesWithDetails m
WHERE 
    m.production_year >= 2000;
