WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
DirectorRoles AS (
    SELECT 
        ci.movie_id,
        c.person_id,
        r.role AS director_role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY c.person_id) AS director_order
    FROM 
        cast_info ci
    JOIN 
        role_type r ON r.id = ci.role_id
    JOIN 
        aka_name c ON c.person_id = ci.person_id
    WHERE 
        r.role = 'director'
),
MovieCompanyInfo AS (
    SELECT 
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type,
        COALESCE(mc.note, 'No notes') AS company_notes
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON co.id = mc.company_id
    JOIN 
        company_type ct ON ct.id = mc.company_type_id
),
MovieKeywordInfo AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON k.id = mk.keyword_id
    GROUP BY 
        mk.movie_id
),
SelectedMovies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        dr.person_id AS director_id,
        mk.keywords,
        mc.company_name,
        mc.company_type,
        mc.company_notes
    FROM 
        RankedMovies rm
    LEFT JOIN 
        DirectorRoles dr ON dr.movie_id = rm.movie_id
    LEFT JOIN 
        MovieCompanyInfo mc ON mc.movie_id = rm.movie_id
    LEFT JOIN 
        MovieKeywordInfo mk ON mk.movie_id = rm.movie_id
    WHERE 
        (dr.director_order IS NULL OR dr.director_order = 1)
        AND rm.title_rank <= 5
)
SELECT 
    sm.movie_id,
    sm.title,
    sm.production_year,
    COALESCE(DENSE_RANK() OVER (PARTITION BY sm.production_year ORDER BY sm.title), 0) AS title_dense_rank,
    COALESCE(sm.director_id, -1) AS director_id,
    COALESCE(sm.keywords, 'No keywords') AS keywords,
    COALESCE(sm.company_name, 'Independent') AS company_name,
    COALESCE(sm.company_type, 'N/A') AS company_type,
    COALESCE(sm.company_notes, 'No information available') AS company_notes
FROM 
    SelectedMovies sm;
