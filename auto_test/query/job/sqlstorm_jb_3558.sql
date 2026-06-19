
WITH ranked_titles AS (
    SELECT
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY b.nr_order ASC) AS rank_order
    FROM
        aka_title a
    JOIN
        movie_companies mc ON a.id = mc.movie_id
    JOIN
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN
        cast_info b ON a.id = b.movie_id
    WHERE
        cn.country_code = 'USA'
        AND a.production_year IS NOT NULL
),
keywords_with_counts AS (
    SELECT
        mk.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM
        movie_keyword mk
    GROUP BY
        mk.movie_id
),
filtered_keywords AS (
    SELECT
        a.id AS movie_id,
        COALESCE(k.keyword, 'No Keyword') AS keyword,
        kc.keyword_count
    FROM
        aka_title a
    LEFT JOIN
        keywords_with_counts kc ON a.id = kc.movie_id
    LEFT JOIN
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
)
SELECT
    rt.title,
    rt.production_year,
    rt.rank_order,
    fk.keyword,
    COALESCE(fk.keyword_count, 0) AS keyword_count
FROM
    ranked_titles rt
FULL OUTER JOIN
    filtered_keywords fk ON rt.title = fk.keyword
WHERE
    rt.rank_order <= 5 OR COALESCE(fk.keyword_count, 0) > 0;
