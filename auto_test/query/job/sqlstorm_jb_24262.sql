WITH RecursiveCast AS (
    SELECT
        c.movie_id,
        c.person_id,
        c.role_id,
        c.nr_order,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY c.nr_order) AS rn
    FROM
        cast_info c
    WHERE
        c.nr_order IS NOT NULL
),
TitleProduction AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
CompanyDetails AS (
    SELECT
        m.movie_id,
        co.name AS company_name,
        ct.kind AS company_type,
        m.note
    FROM
        movie_companies m
    JOIN
        company_name co ON m.company_id = co.id
    JOIN
        company_type ct ON m.company_type_id = ct.id
),
KeywordCount AS (
    SELECT
        mk.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM
        movie_keyword mk
    GROUP BY
        mk.movie_id
),
FinalResults AS (
    SELECT
        t.title AS movie_title,
        t.production_year,
        c.person_id,
        a.name AS actor_name,
        cd.company_name,
        cd.company_type,
        kc.keyword_count,
        COALESCE(kc.keyword_count, 0) AS keywords_present,
        CASE
            WHEN kc.keyword_count > 0 THEN 'Contains Keywords'
            ELSE 'No Keywords'
        END AS keyword_status
    FROM
        TitleProduction t
    JOIN
        RecursiveCast c ON t.title_id = c.movie_id
    LEFT JOIN
        aka_name a ON c.person_id = a.person_id
    LEFT JOIN
        CompanyDetails cd ON t.title_id = cd.movie_id
    LEFT JOIN
        KeywordCount kc ON t.title_id = kc.movie_id
    WHERE
        (t.production_year > 2000 OR cd.company_type IS NULL)
        AND (c.nr_order < 5 OR c.nr_order IS NULL)
)
SELECT 
    movie_title,
    production_year,
    actor_name,
    company_name,
    company_type,
    keywords_present,
    keyword_status
FROM 
    FinalResults
WHERE
    keyword_status = 'Contains Keywords';
