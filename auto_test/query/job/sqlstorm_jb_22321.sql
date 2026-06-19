WITH RankedMovies AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank_by_title,
        COUNT(c.id) OVER (PARTITION BY t.id) AS total_cast_members
    FROM
        aka_title t
    LEFT JOIN
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN
        cast_info c ON c.movie_id = t.id
    WHERE
        t.production_year IS NOT NULL
        AND (t.title IS NOT NULL OR t.title LIKE '%(Unreleased)%')
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
),
CompanyDetails AS (
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
DetailedMovies AS (
    SELECT
        rm.movie_id,
        rm.title,
        rm.production_year,
        rm.rank_by_title,
        COALESCE(mk.keywords, 'No keywords') AS keywords,
        COALESCE(cd.company_name, 'Independent') AS production_company
    FROM
        RankedMovies rm
    LEFT JOIN
        MovieKeywords mk ON rm.movie_id = mk.movie_id
    LEFT JOIN
        CompanyDetails cd ON rm.movie_id = cd.movie_id
)
SELECT
    dm.movie_id,
    dm.title,
    dm.production_year,
    dm.rank_by_title,
    dm.keywords,
    dm.production_company,
    CASE
        WHEN dm.rank_by_title <= 5 THEN 'Top 5'
        WHEN dm.rank_by_title <= 10 THEN 'Top 10'
        ELSE 'Other'
    END AS title_rank_category
FROM
    DetailedMovies dm
WHERE
    dm.production_year BETWEEN 2000 AND 2023
    AND (dm.keywords LIKE '%Action%' OR dm.keywords LIKE '%Drama%')
    OR (dm.production_company IS NULL);
