WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorRoles AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        rt.role AS role,
        ci.nr_order,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        cast_info ci
    JOIN
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN
        role_type rt ON ci.role_id = rt.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        string_agg(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
),
CompleteMovieList AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        ar.actor_name,
        ar.role,
        ar.actor_rank,
        mk.keywords
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorRoles ar ON rm.movie_id = ar.movie_id
    LEFT JOIN 
        MovieKeywords mk ON rm.movie_id = mk.movie_id
    WHERE 
        (ar.role IS NOT NULL OR mk.keywords IS NOT NULL)
)

SELECT 
    movie.movie_id,
    movie.title,
    movie.production_year,
    COALESCE(movie.actor_name, 'No Actors') AS actor_name,
    COALESCE(movie.role, 'No Role') AS role,
    movie.actor_rank,
    COALESCE(movie.keywords, 'No Keywords') AS keywords,
    CASE 
        WHEN movie.production_year < 2000 THEN 'Classic'
        WHEN movie.production_year >= 2000 AND movie.production_year <= 2010 THEN 'Modern'
        ELSE 'Recent'
    END AS era
FROM 
    CompleteMovieList movie
WHERE 
    movie.actor_rank <= 3;
