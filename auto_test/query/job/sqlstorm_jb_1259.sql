WITH RankedTitles AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
),
FilteredMovies AS (
    SELECT 
        mt.movie_id, 
        mt.company_id, 
        cn.name AS company_name,
        mt.note AS company_note
    FROM 
        movie_companies mt
    LEFT JOIN 
        company_name cn ON mt.company_id = cn.id 
    WHERE 
        cn.country_code IS NOT NULL
),
MovieCast AS (
    SELECT 
        ci.movie_id, 
        ak.name AS actor_name, 
        ci.nr_order,
        role.role AS actor_role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id 
    LEFT JOIN 
        role_type role ON ci.role_id = role.id
),
CombinedInfo AS (
    SELECT 
        ft.movie_id, 
        ft.company_name, 
        ft.company_note,
        mv.title,
        mv.production_year,
        mc.actor_name,
        mc.actor_role
    FROM 
        FilteredMovies ft
    JOIN 
        RankedTitles mv ON ft.movie_id = mv.title_id
    LEFT JOIN 
        MovieCast mc ON ft.movie_id = mc.movie_id
    WHERE 
        mv.title_rank <= 5 AND 
        mv.production_year >= 2000
)
SELECT 
    ci.company_name, 
    ci.title, 
    ci.actor_name, 
    COALESCE(ci.actor_role, 'Unspecified') AS actor_role,
    COUNT(*) OVER (PARTITION BY ci.company_name ORDER BY ci.title) AS title_count,
    STRING_AGG(DISTINCT ci.title, ', ') FILTER (WHERE ci.actor_role IS NOT NULL) AS titles_with_roles
FROM 
    CombinedInfo ci
GROUP BY 
    ci.company_name, 
    ci.title, 
    ci.actor_name, 
    ci.actor_role;
