
WITH movie_details AS (
    SELECT
        m.id AS movie_id,
        m.title AS movie_title,
        a.name AS director_name,
        k.keyword AS movie_keyword,
        m.production_year AS year,
        c.kind AS company_type,
        COUNT(mk.id) AS keyword_count
    FROM
        aka_title m
    LEFT JOIN
        movie_companies mc ON m.id = mc.movie_id
    LEFT JOIN
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN
        company_type c ON mc.company_type_id = c.id
    LEFT JOIN
        cast_info ci ON m.id = ci.movie_id
    LEFT JOIN
        aka_name a ON ci.person_id = a.person_id AND a.md5sum IS NOT NULL
    LEFT JOIN
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        m.id, m.title, a.name, k.keyword, m.production_year, c.kind
),
ranked_movies AS (
    SELECT
        md.*,
        ROW_NUMBER() OVER (PARTITION BY md.year ORDER BY md.keyword_count DESC) AS rank
    FROM
        movie_details md
)
SELECT
    rm.movie_id,
    rm.movie_title,
    rm.director_name,
    rm.movie_keyword,
    rm.year,
    rm.company_type,
    rm.keyword_count
FROM
    ranked_movies rm
WHERE
    rm.rank <= 10;
