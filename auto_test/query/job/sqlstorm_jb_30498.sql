WITH RECURSIVE ActorHierarchy AS (
    SELECT 
        c.person_id, 
        a.name AS actor_name, 
        0 AS level
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    WHERE 
        c.movie_id IN (SELECT id FROM aka_title WHERE title LIKE '%Avengers%')
    
    UNION ALL
    
    SELECT 
        c2.person_id,
        a2.name AS actor_name,
        ah.level + 1
    FROM 
        ActorHierarchy ah
    JOIN 
        cast_info c2 ON ah.person_id = c2.person_id
    JOIN 
        aka_name a2 ON c2.person_id = a2.person_id
    WHERE 
        c2.movie_id IN (SELECT id FROM aka_title WHERE title LIKE '%Avengers%') AND 
        ah.level < 3
),
MovieDetails AS (
    SELECT 
        m.title AS movie_title,
        m.production_year,
        k.keyword AS movie_keyword,
        COUNT(distinct c.person_id) AS actor_count
    FROM 
        aka_title m
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        cast_info c ON c.movie_id = m.id
    GROUP BY 
        m.title, m.production_year, k.keyword
),
TopMovies AS (
    SELECT 
        movie_title,
        production_year,
        actor_count,
        ROW_NUMBER() OVER (ORDER BY actor_count DESC) AS rn
    FROM 
        MovieDetails
)
SELECT 
    tm.movie_title,
    tm.production_year,
    tm.actor_count,
    ah.actor_name,
    COALESCE(NULLIF(ah.actor_name, ''), 'Unknown Actor') AS safe_actor_name,
    CASE 
        WHEN ah.level IS NULL THEN 'No Actor'
        ELSE CONCAT(ah.actor_name, ' - Level ', ah.level)
    END AS actor_hierarchy
FROM 
    TopMovies tm
LEFT JOIN 
    ActorHierarchy ah ON tm.actor_count > 0
WHERE 
    tm.rn <= 10;
