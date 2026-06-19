WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
CastCounts AS (
    SELECT
        c.movie_id,
        COUNT(c.id) AS cast_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
CompanyDetails AS (
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
),
FilteredMovies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        cc.cast_count,
        COALESCE(cd.company_name, 'No Company') AS company_name,
        COALESCE(cd.company_type, 'Unknown Type') AS company_type
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CastCounts cc ON rm.movie_id = cc.movie_id
    LEFT JOIN 
        CompanyDetails cd ON rm.movie_id = cd.movie_id AND cd.company_rank = 1
)
SELECT
    fm.title,
    fm.production_year,
    fm.cast_count,
    fm.company_name,
    fm.company_type
FROM 
    FilteredMovies fm
WHERE 
    fm.cast_count > 0;
