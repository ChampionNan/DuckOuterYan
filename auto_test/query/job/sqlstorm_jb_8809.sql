WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.kind_id ORDER BY t.production_year DESC) AS rank
    FROM 
        title t
    JOIN 
        aka_title at ON t.id = at.movie_id
    WHERE 
        at.production_year >= 2000
),
FeaturedActors AS (
    SELECT 
        ak.name AS actor_name,
        ca.movie_id,
        RANK() OVER (PARTITION BY ca.movie_id ORDER BY ak.name) AS actor_rank
    FROM 
        cast_info ca
    JOIN 
        aka_name ak ON ca.person_id = ak.person_id
    WHERE 
        ak.name_pcode_nf IS NOT NULL
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
        c.country_code = 'USA'
)
SELECT 
    rt.title,
    rt.production_year,
    fa.actor_name,
    cd.company_name,
    cd.company_type
FROM 
    RankedTitles rt
LEFT JOIN 
    FeaturedActors fa ON rt.title_id = fa.movie_id AND fa.actor_rank <= 3
LEFT JOIN 
    CompanyDetails cd ON rt.title_id = cd.movie_id
WHERE 
    rt.rank <= 5;
