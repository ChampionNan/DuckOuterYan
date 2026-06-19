WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM title t
    WHERE t.production_year IS NOT NULL
),
MovieDetails AS (
    SELECT 
        mt.movie_id, 
        mt.company_id, 
        cn.name AS company_name, 
        ct.kind AS company_type, 
        mi.info AS movie_info
    FROM movie_companies mt
    JOIN company_name cn ON mt.company_id = cn.id
    JOIN company_type ct ON mt.company_type_id = ct.id
    JOIN movie_info mi ON mt.movie_id = mi.movie_id 
    WHERE mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Synopsis')
),
ActorDetails AS (
    SELECT 
        ci.movie_id, 
        ak.name AS actor_name, 
        ak.person_id, 
        rt.role AS role_name
    FROM cast_info ci 
    JOIN aka_name ak ON ci.person_id = ak.person_id
    JOIN role_type rt ON ci.role_id = rt.id
),
FinalReport AS (
    SELECT 
        rt.title, 
        rt.production_year, 
        md.company_name, 
        md.company_type, 
        ad.actor_name, 
        ad.role_name
    FROM RankedTitles rt
    LEFT JOIN MovieDetails md ON rt.title_id = md.movie_id
    LEFT JOIN ActorDetails ad ON md.movie_id = ad.movie_id
)
SELECT 
    title, 
    production_year, 
    company_name, 
    company_type, 
    actor_name, 
    role_name 
FROM FinalReport
WHERE production_year > 2000;
