WITH RankedTitles AS (
    SELECT 
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.kind_id ORDER BY at.production_year DESC) AS rank
    FROM 
        aka_title at
    WHERE 
        at.production_year IS NOT NULL
),
MovieDetails AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        co.name AS company_name,
        mt.production_year,
        COUNT(DISTINCT kc.keyword) AS keyword_count
    FROM 
        title mt
    LEFT JOIN 
        movie_companies mc ON mt.id = mc.movie_id
    LEFT JOIN 
        company_name co ON mc.company_id = co.id
    LEFT JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    LEFT JOIN 
        keyword kc ON mk.keyword_id = kc.id
    GROUP BY 
        mt.id, co.name, mt.title, mt.production_year
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    md.company_name,
    md.keyword_count,
    rt.rank
FROM 
    MovieDetails md
LEFT JOIN 
    RankedTitles rt ON md.title = rt.title AND md.production_year = rt.production_year
WHERE 
    md.keyword_count > 2;
