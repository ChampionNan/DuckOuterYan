WITH RankedMovies AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.id ASC) AS movie_rank
    FROM
        aka_title m
    WHERE
        m.production_year IS NOT NULL
),

ActorRoles AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        rt.role AS role_name,
        ci.nr_order
    FROM
        cast_info ci
    JOIN aka_name ak ON ci.person_id = ak.person_id
    JOIN role_type rt ON ci.role_id = rt.id
),

CompanyInfo AS (
    SELECT
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY cn.name) AS company_rank
    FROM
        movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
),

MovieKeywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
),

CompleteMovieInfo AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        ar.actor_name,
        ar.role_name,
        ci.company_name,
        ci.company_type,
        mk.keywords
    FROM
        RankedMovies rm
    LEFT JOIN ActorRoles ar ON rm.movie_id = ar.movie_id AND ar.nr_order = 1
    LEFT JOIN CompanyInfo ci ON rm.movie_id = ci.movie_id AND ci.company_rank = 1
    LEFT JOIN MovieKeywords mk ON rm.movie_id = mk.movie_id
)

SELECT
    cmi.title,
    cmi.production_year,
    COALESCE(cmi.actor_name, 'Unknown Actor') AS actor_name,
    COALESCE(cmi.role_name, 'Unknown Role') AS role_name,
    COALESCE(cmi.company_name, 'No Company') AS company_name,
    COALESCE(cmi.company_type, 'N/A') AS company_type,
    COALESCE(cmi.keywords, 'No Keywords') AS keywords
FROM
    CompleteMovieInfo cmi
WHERE
    cmi.production_year BETWEEN 2000 AND 2023
    AND (cmi.keywords IS NOT NULL OR cmi.actor_name IS NOT NULL);
