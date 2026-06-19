
WITH MovieDetails AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        COALESCE(k.keyword, 'Unknown') AS keyword,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year > 2000
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM 
        cast_info ci
    GROUP BY 
        ci.movie_id
),
CompanyInfo AS (
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
),
AggregatedData AS (
    SELECT 
        md.title_id,
        md.title,
        md.production_year,
        md.keyword,
        cd.cast_count,
        ci.company_name,
        ci.company_type,
        RANK() OVER (PARTITION BY md.production_year ORDER BY cd.cast_count DESC) AS rank_by_cast
    FROM 
        MovieDetails md
    LEFT JOIN 
        CastDetails cd ON md.title_id = cd.movie_id
    LEFT JOIN 
        CompanyInfo ci ON md.title_id = ci.movie_id
)
SELECT 
    ad.title,
    ad.production_year,
    ad.keyword,
    ad.cast_count,
    ad.company_name,
    ad.company_type,
    CASE 
        WHEN ad.rank_by_cast IS NULL THEN 'No cast info'
        ELSE CAST(ad.rank_by_cast AS VARCHAR)
    END AS cast_rank
FROM 
    AggregatedData ad
WHERE 
    ad.cast_count IS NOT NULL OR ad.company_name IS NOT NULL;
