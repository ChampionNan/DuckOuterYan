WITH RankedMovies AS (
    SELECT
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        ROW_NUMBER() OVER (PARTITION BY mt.production_year ORDER BY mt.title) AS year_rank
    FROM
        aka_title mt
    WHERE
        mt.production_year BETWEEN 2000 AND 2020
),
CastDetails AS (
    SELECT
        ci.movie_id,
        ak.name AS actor_name,
        ak.id AS actor_id,
        ci.nr_order
    FROM
        cast_info ci
    JOIN aka_name ak ON ci.person_id = ak.person_id
    WHERE
        ci.nr_order < 3
),
CompanyDetails AS (
    SELECT
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
    JOIN company_type ct ON mc.company_type_id = ct.id
),
MovieInfo AS (
    SELECT
        mi.movie_id,
        STRING_AGG(mi.info, '; ') AS movie_info
    FROM
        movie_info mi
    GROUP BY
        mi.movie_id
)
SELECT
    rm.title AS movie_title,
    rm.production_year,
    cd.actor_name,
    cd.nr_order,
    COALESCE(cd.actor_name, 'Unknown Actor') AS verified_actor,
    COALESCE(cn.company_name, 'No Company') AS production_company,
    COALESCE(ci.movie_info, 'No Info Available') AS additional_info
FROM
    RankedMovies rm
LEFT JOIN
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN
    CompanyDetails cn ON rm.movie_id = cn.movie_id
LEFT JOIN
    MovieInfo ci ON rm.movie_id = ci.movie_id
WHERE
    rm.year_rank <= 5;
