WITH RecursiveMovieInfo AS (
    SELECT 
        mt.id AS movie_id,
        mt.title AS original_title,
        mt.production_year,
        k.keyword AS keyword,
        ROW_NUMBER() OVER (PARTITION BY mt.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        aka_title mt
    LEFT JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        mt.production_year IS NOT NULL
        AND mt.kind_id BETWEEN 1 AND 10 
),
ActorInfo AS (
    SELECT 
        ak.name AS actor_name,
        ac.movie_id,
        COUNT(ac.id) AS role_count
    FROM 
        aka_name ak
    JOIN 
        cast_info ac ON ak.person_id = ac.person_id
    WHERE 
        ak.name IS NOT NULL
    GROUP BY 
        ak.name, ac.movie_id
),
CompanyInfo AS (
    SELECT 
        mc.movie_id,
        COALESCE(cn.name, 'Unknown Company') AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
FilteredData AS (
    SELECT 
        rm.movie_id,
        rm.original_title,
        rm.production_year,
        ai.actor_name,
        ci.company_name,
        ci.company_type,
        rm.keyword,
        rm.keyword_rank
    FROM 
        RecursiveMovieInfo rm
    LEFT JOIN 
        ActorInfo ai ON rm.movie_id = ai.movie_id
    LEFT JOIN 
        CompanyInfo ci ON rm.movie_id = ci.movie_id
    WHERE 
        (rm.keyword_rank <= 3 OR ai.role_count IS NULL OR ai.role_count > 2)
        AND rm.production_year < 2020
),
RankedMovies AS (
    SELECT 
        *,
        RANK() OVER (PARTITION BY company_type ORDER BY production_year DESC) AS production_rank
    FROM 
        FilteredData
)
SELECT 
    fm.original_title,
    fm.production_year,
    fm.actor_name,
    fm.company_name,
    fm.company_type,
    CASE 
        WHEN fm.keyword IS NOT NULL AND fm.keyword_rank = 1 THEN 'Primary Keyword Present'
        WHEN fm.keyword IS NULL THEN 'No Keywords'
        ELSE 'Secondary Keyword'
    END AS keyword_status
FROM 
    RankedMovies fm
WHERE 
    (fm.company_type IS NOT NULL OR fm.actor_name IS NOT NULL)
    AND (fm.production_rank < 5 OR fm.production_year BETWEEN 2000 AND 2010);
