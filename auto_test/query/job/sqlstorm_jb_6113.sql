WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        kt.kind AS title_kind,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM 
        title t
    JOIN 
        kind_type kt ON t.kind_id = kt.id
),
AkaNames AS (
    SELECT 
        ak.person_id,
        ak.name AS aka_name
    FROM 
        aka_name ak
    WHERE 
        ak.name IS NOT NULL
),
MovieCast AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        r.role AS person_role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS cast_order
    FROM 
        cast_info ci
    JOIN 
        role_type r ON ci.role_id = r.id
),
MovieCompanies AS (
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
FilteredMovies AS (
    SELECT 
        rt.title,
        rt.production_year,
        ak.aka_name,
        mc.company_name,
        mc.company_type,
        CAST(mo.info AS TEXT) AS info_detail
    FROM 
        RankedTitles rt
    LEFT JOIN 
        AkaNames ak ON rt.title_id = ak.person_id
    LEFT JOIN 
        MovieCast mcast ON rt.title_id = mcast.movie_id
    LEFT JOIN 
        MovieCompanies mc ON rt.title_id = mc.movie_id
    LEFT JOIN 
        movie_info mo ON rt.title_id = mo.movie_id
    WHERE 
        rt.rn <= 5
)
SELECT 
    title,
    production_year,
    aka_name,
    company_name,
    company_type,
    info_detail
FROM 
    FilteredMovies
WHERE 
    production_year >= 2000;
