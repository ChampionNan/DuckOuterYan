WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY t.production_year DESC) AS rn
    FROM 
        aka_title m
    JOIN 
        title t ON m.movie_id = t.id
    WHERE 
        m.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
        AND t.production_year IS NOT NULL
), MovieDetails AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year,
        COALESCE(ki.keyword, 'Unknown') AS keyword,
        COUNT(ci.person_id) AS cast_count
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_keyword mk ON rm.movie_id = mk.movie_id
    LEFT JOIN 
        keyword ki ON mk.keyword_id = ki.id
    LEFT JOIN 
        cast_info ci ON rm.movie_id = ci.movie_id
    GROUP BY 
        rm.movie_id, rm.title, rm.production_year, ki.keyword
), CompanyDetails AS (
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
), DetailedReport AS (
    SELECT 
        md.title, 
        md.production_year,
        md.keyword,
        md.cast_count,
        COALESCE(cd.company_name, 'Independent') AS company_name,
        COALESCE(cd.company_type, 'N/A') AS company_type
    FROM 
        MovieDetails md
    LEFT JOIN 
        CompanyDetails cd ON md.movie_id = cd.movie_id
)
SELECT 
    title, 
    production_year, 
    keyword, 
    cast_count,
    company_name,
    company_type
FROM 
    DetailedReport
WHERE 
    (cast_count > 5 OR keyword IS NOT NULL);
