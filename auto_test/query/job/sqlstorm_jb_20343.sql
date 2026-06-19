WITH RankedMovies AS (
    SELECT 
        at.id AS title_id,
        at.title,
        at.production_year,
        COALESCE(cn.name, 'Unknown Company') AS production_company,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC) AS year_rank
    FROM 
        aka_title at
    LEFT JOIN 
        movie_companies mc ON at.movie_id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        at.production_year IS NOT NULL
),
ActorRole AS (
    SELECT 
        ak.name AS actor_name,
        ar.movie_id,
        rt.role
    FROM 
        cast_info ar
    JOIN 
        aka_name ak ON ar.person_id = ak.person_id
    JOIN 
        role_type rt ON ar.role_id = rt.id
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
),
FilteredMovies AS (
    SELECT 
        rm.title_id,
        rm.title,
        rm.production_year,
        ar.actor_name,
        mk.keywords,
        rm.production_company
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorRole ar ON rm.title_id = ar.movie_id
    LEFT JOIN 
        MovieKeywords mk ON rm.title_id = mk.movie_id
    WHERE 
        rm.year_rank <= 5 AND
        (ar.role IS NULL OR ar.role LIKE '%lead%') AND
        rm.production_company <> 'Unknown Company'
)
SELECT 
    fm.title,
    fm.production_year,
    fm.production_company,
    COALESCE(fm.actor_name, 'No Lead Actor') AS lead_actor,
    COALESCE(fm.keywords, 'No Keywords') AS movie_keywords,
    CASE 
        WHEN fm.production_company IS NOT NULL THEN 'Company Exists' 
        ELSE 'Company Not Found' 
    END AS company_status
FROM 
    FilteredMovies fm;
