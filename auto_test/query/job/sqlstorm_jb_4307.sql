
WITH RankedTitles AS (
    SELECT 
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.kind_id ORDER BY t.production_year DESC) AS rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
TopRankedTitles AS (
    SELECT 
        title,
        production_year,
        kind_id
    FROM 
        RankedTitles
    WHERE 
        rank <= 5
),
CompanyInfo AS (
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
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    t.title,
    t.production_year,
    ci.company_name,
    ci.company_type,
    mk.keywords
FROM 
    TopRankedTitles t
LEFT JOIN 
    CompanyInfo ci ON t.kind_id = ci.movie_id
LEFT JOIN 
    MovieKeywords mk ON t.kind_id = mk.movie_id
WHERE 
    ci.company_name IS NOT NULL OR mk.keywords IS NOT NULL;
