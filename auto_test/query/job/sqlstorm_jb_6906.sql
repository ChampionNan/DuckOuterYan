WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        ca.person_id,
        ca.movie_id,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY ca.person_id, ca.movie_id ORDER BY ca.nr_order) AS role_rank
    FROM 
        cast_info ca
    JOIN 
        role_type r ON ca.role_id = r.id
),
CompanyNames AS (
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
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        k.keyword
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
FinalResults AS (
    SELECT 
        rt.title,
        rt.production_year,
        ar.person_id,
        ar.role_name,
        cn.company_name,
        cn.company_type,
        mk.keyword
    FROM 
        RankedTitles rt
    JOIN 
        complete_cast cc ON rt.title_id = cc.movie_id
    LEFT JOIN 
        ActorRoles ar ON cc.subject_id = ar.person_id AND cc.movie_id = ar.movie_id
    LEFT JOIN 
        CompanyNames cn ON cc.movie_id = cn.movie_id
    LEFT JOIN 
        MovieKeywords mk ON cc.movie_id = mk.movie_id
)
SELECT 
    title, 
    production_year, 
    person_id, 
    role_name, 
    company_name, 
    company_type, 
    string_agg(keyword, ', ') AS keywords
FROM 
    FinalResults
GROUP BY 
    title, production_year, person_id, role_name, company_name, company_type;
