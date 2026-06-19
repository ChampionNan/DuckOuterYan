
WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank,
        COUNT(c.person_id) AS cast_count
    FROM 
        aka_title a
    LEFT JOIN 
        cast_info c ON a.id = c.movie_id
    WHERE 
        a.production_year IS NOT NULL
    GROUP BY 
        a.title, a.production_year
),
ActorDetails AS (
    SELECT 
        ak.name AS actor_name,
        cm.name AS company_name,
        ct.kind AS company_type,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.title ORDER BY ak.name) AS actor_order
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        aka_title m ON ci.movie_id = m.id
    LEFT JOIN 
        movie_companies mc ON m.id = mc.movie_id
    LEFT JOIN 
        company_name cm ON mc.company_id = cm.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    rm.title,
    rm.production_year,
    rm.cast_count,
    ad.actor_name,
    ad.company_name,
    ad.company_type
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorDetails ad ON rm.title = ad.title AND rm.production_year = ad.production_year
WHERE 
    rm.year_rank <= 10;
