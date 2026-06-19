WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.kind AS company_kind,
        a.name AS actor_name,
        COUNT(DISTINCT k.keyword) AS keyword_count
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_type c ON mc.company_type_id = c.id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        t.id, t.title, t.production_year, c.kind, a.name
),
RankedMovies AS (
    SELECT 
        movie_title,
        production_year,
        company_kind,
        actor_name,
        keyword_count,
        RANK() OVER (PARTITION BY production_year ORDER BY keyword_count DESC) AS rank_within_year
    FROM 
        MovieDetails
)
SELECT 
    movie_title,
    production_year,
    company_kind,
    actor_name,
    keyword_count
FROM 
    RankedMovies
WHERE 
    rank_within_year <= 5;
