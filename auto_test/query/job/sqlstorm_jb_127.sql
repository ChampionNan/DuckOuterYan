
WITH MovieDetails AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.id, t.title, t.production_year, k.keyword
),
CompanyInfo AS (
    SELECT 
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON mc.company_id = co.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
TopMovies AS (
    SELECT 
        md.title_id,
        md.title,
        md.production_year,
        md.keyword,
        md.actor_count,
        ROW_NUMBER() OVER (PARTITION BY md.keyword ORDER BY md.actor_count DESC) AS rn
    FROM 
        MovieDetails md
)
SELECT 
    tm.title,
    tm.production_year,
    tm.keyword,
    ci.company_name,
    ci.company_type,
    tm.actor_count
FROM 
    TopMovies tm
LEFT JOIN 
    CompanyInfo ci ON tm.title_id = ci.movie_id
WHERE 
    tm.rn = 1;
