WITH RankedMovies AS (
    SELECT 
        a.id AS aka_id,
        t.id AS title_id,
        t.title,
        t.production_year,
        COALESCE(ci.note, 'No role noted') AS role_note,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM aka_title t
    LEFT JOIN cast_info ci ON t.id = ci.movie_id
    LEFT JOIN aka_name a ON ci.person_id = a.person_id
    WHERE t.production_year IS NOT NULL
),
FilteredCompanies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS company_rank
    FROM movie_companies mc
    INNER JOIN company_name c ON mc.company_id = c.id
    INNER JOIN company_type ct ON mc.company_type_id = ct.id
    WHERE c.country_code = 'USA' AND ct.kind IS NOT NULL
),
MoviesWithRoles AS (
    SELECT 
        rm.title_id,
        rm.title,
        rm.production_year,
        STRING_AGG(DISTINCT ci.note, ', ') AS roles
    FROM RankedMovies rm
    LEFT JOIN cast_info ci ON rm.title_id = ci.movie_id
    GROUP BY rm.title_id, rm.title, rm.production_year
),
FinalOutput AS (
    SELECT 
        mw.title,
        mw.production_year,
        COALESCE(fc.company_name, 'No company') AS company_name,
        mw.roles,
        CASE 
            WHEN mw.production_year < 2000 THEN 'Classic'
            WHEN mw.production_year >= 2000 AND mw.production_year < 2010 THEN 'Modern'
            ELSE 'Recent'
        END AS Era,
        CASE WHEN mw.roles IS NULL THEN 'None' ELSE 'Exists' END AS Role_Status
    FROM MoviesWithRoles mw
    LEFT JOIN FilteredCompanies fc ON mw.title_id = fc.movie_id AND fc.company_rank = 1
    WHERE mw.roles IS NOT NULL OR fc.company_name IS NOT NULL
)
SELECT 
    title,
    production_year,
    company_name,
    roles,
    Era,
    Role_Status
FROM FinalOutput
WHERE NOT (Title LIKE '%Episode%' OR company_name = 'No company');
