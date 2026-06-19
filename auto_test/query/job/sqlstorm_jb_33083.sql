WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        FALSE AS is_root
    FROM 
        aka_title m
    WHERE 
        m.kind_id = 1  
    
    UNION ALL
    
    SELECT 
        mc.linked_movie_id AS movie_id,
        at.title,
        at.production_year,
        TRUE AS is_root
    FROM 
        movie_link mc
    JOIN 
        aka_title at ON mc.linked_movie_id = at.id
    JOIN 
        MovieHierarchy mh ON mc.movie_id = mh.movie_id
    WHERE 
        mh.is_root = FALSE
),
MovieKeywords AS (
    SELECT 
        mt.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mt
    JOIN 
        keyword k ON mt.keyword_id = k.id
    GROUP BY 
        mt.movie_id
),
MovieCompanyInfo AS (
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
RankedMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        mk.keywords,
        mc.company_name,
        mc.company_type,
        ROW_NUMBER() OVER (PARTITION BY mh.production_year ORDER BY mh.production_year DESC) AS movie_rank
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        MovieKeywords mk ON mh.movie_id = mk.movie_id
    LEFT JOIN 
        MovieCompanyInfo mc ON mh.movie_id = mc.movie_id
)
SELECT 
    r.movie_id,
    r.title,
    r.production_year,
    COALESCE(r.keywords, 'No Keywords') AS keywords,
    COALESCE(r.company_name, 'Unknown Company') AS company_name,
    r.company_type,
    r.movie_rank
FROM 
    RankedMovies r
WHERE 
    r.movie_rank <= 10;
