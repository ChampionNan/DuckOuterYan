WITH MovieDetails AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        COALESCE(cn.name, 'Unknown Company') AS company_name,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY t.production_year DESC) AS rn
    FROM
        aka_title t
    LEFT JOIN
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN
        company_name cn ON mc.company_id = cn.id
    WHERE
        t.production_year IS NOT NULL
),
TopMovies AS (
    SELECT
        md.*,
        COUNT(*) OVER (PARTITION BY md.movie_id) AS keyword_count
    FROM
        MovieDetails md
    WHERE
        md.rn = 1
),
FilteredMovies AS (
    SELECT
        *,
        CASE 
            WHEN keyword_count > 3 THEN 'Popular'
            ELSE 'Less Popular'
        END AS popularity
    FROM
        TopMovies
)
SELECT
    f.title,
    f.production_year,
    f.company_name,
    f.keyword AS associated_keyword,
    f.popularity
FROM
    FilteredMovies f
WHERE
    (f.production_year >= 2000 AND f.production_year <= 2023)
    OR (f.company_name IS NULL);
