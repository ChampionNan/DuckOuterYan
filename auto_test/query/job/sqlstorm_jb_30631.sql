WITH RECURSIVE TitleHierarchy AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.season_nr,
        t.episode_nr,
        1 AS level
    FROM 
        aka_title t
    WHERE 
        t.kind_id = 1 
    
    UNION ALL
    
    SELECT 
        t.id,
        t.title,
        t.production_year,
        t.season_nr,
        t.episode_nr,
        th.level + 1
    FROM 
        aka_title t
    INNER JOIN 
        TitleHierarchy th ON t.episode_of_id = th.title_id
),
MovieInfo AS (
    SELECT 
        m.id AS movie_id,
        m.title AS movie_title,
        COALESCE(mi.info, 'No Information') AS movie_info,
        m.production_year
    FROM 
        aka_title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id AND mi.info_type_id = 1 
),
CastDetails AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS actor_role,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_order
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),
CountryCompany AS (
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
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS all_keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    th.title,
    th.production_year,
    mi.movie_info,
    cd.actor_name,
    cd.actor_role,
    cc.company_name,
    cc.company_type,
    mk.all_keywords
FROM 
    TitleHierarchy th
LEFT JOIN 
    MovieInfo mi ON th.title_id = mi.movie_id
LEFT JOIN 
    CastDetails cd ON th.title_id = cd.movie_id
LEFT JOIN 
    CountryCompany cc ON th.title_id = cc.movie_id
LEFT JOIN 
    MovieKeywords mk ON th.title_id = mk.movie_id
WHERE 
    (th.production_year > 2000) AND 
    (cc.company_type IS NOT NULL OR cd.actor_role IS NOT NULL);
