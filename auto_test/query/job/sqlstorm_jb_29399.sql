
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
DistinctKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords_list
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
PersonMovieRoles AS (
    SELECT 
        ci.movie_id, 
        p.name AS person_name,
        rt.role AS role_type,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY p.name) AS role_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name p ON ci.person_id = p.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
),
CombinedInfo AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        COALESCE(dk.keywords_list, 'No Keywords') AS keywords,
        COALESCE(pm.person_name, 'No Cast') AS cast_member,
        pm.role_type AS cast_role,
        rt.title_rank
    FROM 
        RankedTitles rt
    LEFT JOIN 
        DistinctKeywords dk ON rt.title_id = dk.movie_id
    LEFT JOIN 
        PersonMovieRoles pm ON rt.title_id = pm.movie_id
)
SELECT 
    ci.title,
    ci.production_year,
    ci.keywords,
    ci.cast_member,
    ci.cast_role
FROM 
    CombinedInfo ci
WHERE 
    ci.title_rank <= 5;
