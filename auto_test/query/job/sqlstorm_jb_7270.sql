WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id, 
        m.title, 
        m.production_year, 
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY c.nr_order) AS role_rank
    FROM 
        aka_title m
    JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        complete_cast cc ON m.id = cc.movie_id
    JOIN 
        cast_info c ON cc.subject_id = c.id
    WHERE 
        m.production_year > 2000
),
ActorDetails AS (
    SELECT 
        a.name AS actor_name,
        m.movie_id,
        m.title,
        m.production_year
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        RankedMovies m ON ci.movie_id = m.movie_id
    WHERE 
        a.name IS NOT NULL
)
SELECT 
    rd.actor_name,
    rd.title,
    rd.production_year,
    COUNT(DISTINCT km.keyword) AS keyword_count
FROM 
    ActorDetails rd
LEFT JOIN 
    movie_keyword mk ON rd.movie_id = mk.movie_id
LEFT JOIN 
    keyword km ON mk.keyword_id = km.id
GROUP BY 
    rd.actor_name, 
    rd.title, 
    rd.production_year;
