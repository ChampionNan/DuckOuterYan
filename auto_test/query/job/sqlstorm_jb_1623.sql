WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_year,
        COUNT(c.person_id) OVER (PARTITION BY t.id) AS cast_count
    FROM 
        aka_title t
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.id
    WHERE 
        t.production_year IS NOT NULL
),
CompanyDetails AS (
    SELECT 
        m.movie_id, 
        c.name AS company_name, 
        ct.kind AS company_kind,
        ROW_NUMBER() OVER (PARTITION BY m.movie_id ORDER BY ct.kind) AS company_rank
    FROM 
        movie_companies m
    JOIN 
        company_name c ON m.company_id = c.id
    JOIN 
        company_type ct ON m.company_type_id = ct.id
),
TitleKeywords AS (
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
    rt.title, 
    rt.production_year, 
    rt.rank_year, 
    COALESCE(cd.company_name, 'Unknown') AS company_name,
    COALESCE(h.keywords, 'No Keywords') AS keywords,
    rt.cast_count 
FROM 
    RankedTitles rt
LEFT JOIN 
    CompanyDetails cd ON rt.title_id = cd.movie_id AND cd.company_rank = 1
LEFT JOIN 
    TitleKeywords h ON rt.title_id = h.movie_id 
WHERE 
    rt.cast_count > 0;
