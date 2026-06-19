WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY t.production_year DESC) AS title_rank
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.movie_id
    WHERE 
        a.name IS NOT NULL
),
MovieKeywords AS (
    SELECT 
        mt.movie_id, 
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        aka_title mt ON mk.movie_id = mt.movie_id
    WHERE 
        mt.production_year > 2000
    GROUP BY 
        mt.movie_id
),
CompanyDetails AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        c.country_code IS NOT NULL
)
SELECT 
    rt.actor_name,
    rt.movie_title,
    rt.production_year,
    COALESCE(mk.keywords, 'No Keywords') AS keywords,
    cd.company_name,
    cd.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    MovieKeywords mk ON rt.aka_id = mk.movie_id
LEFT JOIN 
    CompanyDetails cd ON rt.aka_id = cd.movie_id
WHERE 
    rt.title_rank = 1;
