WITH RankedMovies AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorMovieCount AS (
    SELECT 
        ca.person_id, 
        COUNT(DISTINCT c.movie_id) AS movie_count
    FROM 
        cast_info c
    JOIN 
        aka_name ca ON c.person_id = ca.person_id
    GROUP BY 
        ca.person_id
),
TopActors AS (
    SELECT 
        a.person_id
    FROM 
        ActorMovieCount a
    WHERE 
        a.movie_count > 10
),
CompanyProduction AS (
    SELECT 
        mc.movie_id, 
        cn.name AS company_name, 
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    t.title,
    t.production_year,
    ca.name AS actor_name,
    tp.company_name,
    tp.company_type
FROM 
    RankedMovies t
LEFT JOIN 
    cast_info ci ON t.title_id = ci.movie_id
LEFT JOIN 
    aka_name ca ON ci.person_id = ca.person_id
LEFT JOIN 
    CompanyProduction tp ON t.title_id = tp.movie_id
WHERE 
    t.year_rank <= 5
    AND (ci.movie_id IS NULL OR ca.id IS NOT NULL)
    AND (tp.company_name LIKE '%Studios%' OR tp.company_type IS NULL);
