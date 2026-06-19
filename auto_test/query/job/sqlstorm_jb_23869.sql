
WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.name AS aka_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS title_rank
    FROM 
        aka_name a
    JOIN 
        cast_info c ON a.person_id = c.person_id
    JOIN 
        aka_title t ON c.movie_id = t.movie_id
    WHERE 
        t.production_year IS NOT NULL
),
FilteredCompanies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS company_rank
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    WHERE 
        c.name IS NOT NULL AND
        c.country_code IS NOT NULL AND
        c.country_code != '' 
),
MovieSummary AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        COALESCE(k.keyword, 'No Keywords') AS keyword,
        COUNT(pc.person_id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info pc ON cc.subject_id = pc.person_id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.id, t.title, t.production_year, k.keyword
),
FinalOutput AS (
    SELECT 
        r.aka_name,
        r.movie_title,
        r.production_year,
        f.company_name,
        f.company_type,
        m.keyword,
        m.cast_count
    FROM 
        RankedTitles r
    LEFT JOIN 
        FilteredCompanies f ON f.movie_id = (SELECT t.id FROM aka_title t WHERE t.title = r.movie_title AND t.production_year = r.production_year LIMIT 1)
    LEFT JOIN 
        MovieSummary m ON r.movie_title = m.title
    WHERE 
        r.title_rank = 1
)
SELECT 
    aka_name,
    movie_title,
    production_year,
    COALESCE(company_name, 'Independent') AS company_name,
    company_type,
    keyword,
    cast_count
FROM 
    FinalOutput
WHERE 
    production_year IS NOT NULL;
