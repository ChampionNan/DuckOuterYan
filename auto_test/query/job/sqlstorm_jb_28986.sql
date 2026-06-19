WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC, t.title) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        ak.person_id,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
),
MoviesWithKeywords AS (
    SELECT 
        rm.movie_id,
        rm.title,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_keyword mk ON rm.movie_id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        rm.movie_id, rm.title
),
MovieInfo AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        cd.actor_name,
        cd.role_rank,
        mwk.keywords
    FROM 
        RankedMovies rm
    JOIN 
        CastDetails cd ON rm.movie_id = cd.movie_id
    LEFT JOIN 
        MoviesWithKeywords mwk ON rm.movie_id = mwk.movie_id
)
SELECT 
    mi.title,
    mi.production_year,
    mi.actor_name,
    mi.role_rank,
    mi.keywords
FROM 
    MovieInfo mi
WHERE 
    mi.production_year BETWEEN 2000 AND 2020;
