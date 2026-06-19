WITH MovieData AS (
    SELECT
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        c.name AS company_name,
        p.name AS person_name,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM
        aka_title t
    LEFT JOIN
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN
        company_name c ON mc.company_id = c.id
    LEFT JOIN
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN
        aka_name p ON ci.person_id = p.person_id
    WHERE
        t.production_year BETWEEN 2000 AND 2023
        AND k.keyword IS NOT NULL
    GROUP BY
        t.id, t.title, t.production_year, k.keyword, c.name, p.name
),
RankedMovies AS (
    SELECT
        md.*,
        ROW_NUMBER() OVER (PARTITION BY md.keyword ORDER BY md.cast_count DESC) AS rank
    FROM
        MovieData md
)
SELECT
    movie_id,
    title,
    production_year,
    keyword,
    company_name,
    person_name,
    cast_count
FROM
    RankedMovies
WHERE
    rank <= 5;
