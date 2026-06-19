
WITH RankedTitles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        COUNT(DISTINCT kc.keyword) AS keyword_count
    FROM
        title t
    LEFT JOIN
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN
        keyword kc ON mk.keyword_id = kc.id
    GROUP BY
        t.id, t.title, t.production_year
),
TopMovies AS (
    SELECT
        rt.title_id,
        rt.title,
        rt.production_year,
        rt.keyword_count,
        RANK() OVER (ORDER BY rt.keyword_count DESC) AS rk
    FROM
        RankedTitles rt
    WHERE
        rt.production_year >= 2000
)
SELECT
    tt.title,
    a1.name AS actor_name,
    ct.kind AS company_type,
    pi.info AS person_additional_info
FROM
    TopMovies tt
JOIN
    complete_cast cc ON tt.title_id = cc.movie_id
JOIN
    cast_info ci ON cc.subject_id = ci.person_id
JOIN
    aka_name a1 ON ci.person_id = a1.person_id
JOIN
    movie_companies mc ON tt.title_id = mc.movie_id
JOIN
    company_type ct ON mc.company_type_id = ct.id
LEFT JOIN
    person_info pi ON ci.person_id = pi.person_id
WHERE
    tt.rk <= 10
    AND a1.name IS NOT NULL
    AND ct.kind IS NOT NULL;
