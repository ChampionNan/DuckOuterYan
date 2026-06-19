WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
FullCast AS (
    SELECT 
        c.movie_id,
        COALESCE(a.name, cn.name) AS actor_name,
        ct.kind AS cast_type
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        comp_cast_type ct ON c.person_role_id = ct.id
    LEFT JOIN 
        company_name cn ON c.movie_id = cn.imdb_id
),
MovieInfo AS (
    SELECT 
        m.movie_id,
        STRING_AGG(mi.info, '; ') AS info_details
    FROM 
        movie_info m
    JOIN 
        movie_info_idx mi ON m.movie_id = mi.movie_id
    GROUP BY 
        m.movie_id
)
SELECT 
    rt.title,
    rt.production_year,
    fc.actor_name,
    fc.cast_type,
    mi.info_details
FROM 
    RankedTitles rt
JOIN 
    FullCast fc ON rt.title_id = fc.movie_id
LEFT JOIN 
    MovieInfo mi ON rt.title_id = mi.movie_id
WHERE 
    rt.rank <= 3;
