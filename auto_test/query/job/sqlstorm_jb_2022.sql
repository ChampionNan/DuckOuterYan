WITH RankedMovies AS (
    SELECT 
        title.id AS movie_id,
        title.title,
        title.production_year,
        ROW_NUMBER() OVER (PARTITION BY title.production_year ORDER BY title.title) AS rank
    FROM 
        title
    WHERE 
        title.production_year IS NOT NULL
),
DirectorCompany AS (
    SELECT 
        cm.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies cm
    JOIN 
        company_name cn ON cm.company_id = cn.id
    JOIN 
        company_type ct ON cm.company_type_id = ct.id
    WHERE 
        ct.kind = 'Distributor'
),
MovieCast AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        rt.role
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
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
    rm.title,
    rm.production_year,
    COALESCE(dc.company_name, 'Independent') AS distributor,
    COALESCE(mk.keywords, 'No keywords') AS keywords,
    mc.actor_name,
    mc.role
FROM 
    RankedMovies rm
LEFT JOIN 
    DirectorCompany dc ON rm.movie_id = dc.movie_id
LEFT JOIN 
    MovieCast mc ON rm.movie_id = mc.movie_id
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    rm.rank <= 5;
