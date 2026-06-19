WITH RankedMovies AS (
    SELECT
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.production_year DESC) AS year_rank
    FROM
        aka_title m
    WHERE
        m.kind_id = (SELECT id FROM kind_type WHERE kind = 'movie')
),
CastDetails AS (
    SELECT
        c.movie_id,
        a.name AS actor_name,
        r.role AS role_name,
        COUNT(c.id) OVER (PARTITION BY c.movie_id) AS cast_count
    FROM
        cast_info c
    JOIN
        aka_name a ON c.person_id = a.person_id
    JOIN
        role_type r ON c.role_id = r.id
    WHERE
        a.md5sum IS NOT NULL
),
CompanyInfo AS (
    SELECT
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
    JOIN
        company_name co ON mc.company_id = co.id
    JOIN
        company_type ct ON mc.company_type_id = ct.id
),
MovieKeywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
)

SELECT
    rm.title,
    rm.production_year,
    cd.actor_name,
    cd.role_name,
    ci.company_name,
    ci.company_type,
    mk.keywords
FROM
    RankedMovies rm
LEFT JOIN
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN
    CompanyInfo ci ON rm.movie_id = ci.movie_id
LEFT JOIN
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE
    rm.year_rank <= 5 AND
    (cd.actor_name IS NOT NULL OR ci.company_name IS NOT NULL);
