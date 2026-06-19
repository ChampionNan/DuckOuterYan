WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY LENGTH(t.title) DESC) AS rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
TopTenTitles AS (
    SELECT 
        title_id, title, production_year 
    FROM 
        RankedTitles 
    WHERE 
        rank <= 10
),
ActorInfo AS (
    SELECT 
        ak.name AS actor_name,
        ci.movie_id
    FROM 
        cast_info ci 
    JOIN 
        aka_name ak ON ak.person_id = ci.person_id
),
MovieCompanyInfo AS (
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
)
SELECT 
    tt.title AS movie_title,
    tt.production_year,
    ai.actor_name,
    mci.company_name,
    mci.company_type
FROM 
    TopTenTitles tt
LEFT JOIN 
    ActorInfo ai ON ai.movie_id = tt.title_id
LEFT JOIN 
    MovieCompanyInfo mci ON mci.movie_id = tt.title_id;
