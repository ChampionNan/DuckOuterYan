WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER(PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_year
    FROM 
        title t 
    WHERE 
        t.production_year IS NOT NULL
), 
ActorRoles AS (
    SELECT 
        ca.person_id,
        ca.movie_id,
        coalesce(ca.note, 'N/A') AS role_note,
        r.role AS role_name
    FROM 
        cast_info ca
    JOIN 
        role_type r ON ca.role_id = r.id
), 
CompanyInfo AS (
    SELECT 
        mc.movie_id, 
        cn.name AS company_name, 
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
), 
MovieKeyword AS (
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
    t.title AS Movie_Title,
    t.production_year AS Release_Year,
    a.name AS Actor_Name,
    ar.role_name AS Role,
    ci.company_name AS Production_Company,
    ci.company_type AS Company_Type,
    mk.keywords AS Movie_Keywords
FROM 
    RankedTitles t
LEFT JOIN 
    ActorRoles ar ON t.title_id = ar.movie_id
LEFT JOIN 
    aka_name a ON ar.person_id = a.person_id
LEFT JOIN 
    CompanyInfo ci ON t.title_id = ci.movie_id
LEFT JOIN 
    MovieKeyword mk ON t.title_id = mk.movie_id
WHERE 
    t.rank_year <= 5;
