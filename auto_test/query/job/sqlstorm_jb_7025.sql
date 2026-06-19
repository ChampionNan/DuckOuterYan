
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        title t 
    WHERE 
        t.production_year BETWEEN 2000 AND 2023
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
MovieDetails AS (
    SELECT 
        r.title_id, 
        r.title, 
        ci.company_name, 
        ci.company_type, 
        k.keyword, 
        r.production_year,
        r.rank
    FROM 
        RankedTitles r
    LEFT JOIN 
        complete_cast cc ON cc.movie_id = r.title_id
    LEFT JOIN 
        CompanyInfo ci ON ci.movie_id = r.title_id
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = r.title_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
)

SELECT 
    md.title, 
    md.production_year, 
    md.company_name, 
    md.company_type, 
    STRING_AGG(DISTINCT md.keyword, ', ') AS keywords
FROM 
    MovieDetails md
WHERE 
    md.rank <= 5
GROUP BY 
    md.title, md.production_year, md.company_name, md.company_type, md.rank;
