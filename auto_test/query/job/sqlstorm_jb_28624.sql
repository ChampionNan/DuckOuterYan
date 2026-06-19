WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.name AS aka_name,
        t.movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    JOIN 
        aka_name a ON t.id = a.id
    WHERE 
        t.production_year >= 2000
),

CastDetails AS (
    SELECT 
        c.id AS cast_id,
        c.movie_id,
        n.name AS actor_name,
        r.role AS role_name,
        c.nr_order
    FROM 
        cast_info c
    JOIN 
        name n ON c.person_id = n.id
    JOIN 
        role_type r ON c.role_id = r.id
    WHERE 
        r.role IN ('Actor', 'Actress')
),

MovieKeywords AS (
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
    rt.production_year,
    rt.title,
    rt.aka_name,
    cd.actor_name,
    cd.role_name,
    mk.keywords,
    rt.title_rank
FROM 
    RankedTitles rt
LEFT JOIN 
    CastDetails cd ON rt.movie_id = cd.movie_id
LEFT JOIN 
    MovieKeywords mk ON rt.movie_id = mk.movie_id
WHERE 
    rt.title_rank <= 5;
