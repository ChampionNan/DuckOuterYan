WITH movie_years AS (
    SELECT
        title.id AS movie_id,
        title.title,
        title.production_year,
        COUNT(DISTINCT cast_info.person_id) AS cast_count
    FROM
        title
    LEFT JOIN
        cast_info ON title.id = cast_info.movie_id
    GROUP BY
        title.id, title.title, title.production_year
),
top_movies AS (
    SELECT
        movie_id,
        title,
        production_year,
        cast_count,
        RANK() OVER (PARTITION BY production_year ORDER BY cast_count DESC) AS rank_per_year
    FROM
        movie_years
),
notable_companies AS (
    SELECT
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY mc.note DESC) AS rn
    FROM
        movie_companies mc
    JOIN
        company_name c ON mc.company_id = c.id
    JOIN
        company_type ct ON mc.company_type_id = ct.id
    WHERE
        c.country_code IS NOT NULL
)
SELECT
    tm.production_year,
    tm.title,
    tm.cast_count,
    nc.company_name,
    nc.company_type
FROM
    top_movies tm
LEFT JOIN
    notable_companies nc ON tm.movie_id = nc.movie_id AND nc.rn = 1
WHERE
    tm.rank_per_year <= 5;
