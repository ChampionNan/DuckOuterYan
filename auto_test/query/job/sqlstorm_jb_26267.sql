
WITH RankedTitles AS (
    SELECT
        a.title,
        a.production_year,
        k.keyword,
        COUNT(DISTINCT mc.company_id) AS company_count,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY a.production_year DESC) AS rank
    FROM
        aka_title a
    LEFT JOIN
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN
        movie_companies mc ON a.id = mc.movie_id
    GROUP BY
        a.id, a.title, a.production_year, k.keyword
),
BestTitles AS (
    SELECT
        title,
        production_year,
        keyword,
        company_count
    FROM
        RankedTitles
    WHERE
        rank = 1
),
FinalResults AS (
    SELECT
        b.title,
        b.production_year,
        b.keyword,
        b.company_count,
        COALESCE(c.name, 'Unknown') AS director_name
    FROM
        BestTitles b
    LEFT JOIN
        cast_info ci ON b.title = (SELECT title FROM aka_title WHERE id = ci.movie_id)
    LEFT JOIN
        aka_name c ON ci.person_id = c.person_id AND ci.person_role_id = (SELECT id FROM role_type WHERE role = 'Director')
)
SELECT
    title,
    production_year,
    keyword,
    company_count,
    director_name
FROM
    FinalResults
WHERE
    company_count > 2;
