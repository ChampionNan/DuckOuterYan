WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY t.production_year DESC) AS rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = t.id
    LEFT JOIN 
        keyword k ON k.id = mk.keyword_id
    WHERE 
        t.production_year >= 2000
),

CastDetails AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS actor_rank
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        role_type r ON c.role_id = r.id
),

MoviesWithCast AS (
    SELECT 
        rm.movie_id, 
        rm.title, 
        rm.production_year,
        rc.actor_name,
        rc.role_name,
        rc.actor_rank
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CastDetails rc ON rm.movie_id = rc.movie_id
    WHERE 
        rm.rank = 1 
)

SELECT 
    mwc.title,
    mwc.production_year,
    STRING_AGG(mwc.actor_name || ' (' || mwc.role_name || ')', ', ') AS cast_list
FROM 
    MoviesWithCast mwc
GROUP BY 
    mwc.movie_id, mwc.title, mwc.production_year;
