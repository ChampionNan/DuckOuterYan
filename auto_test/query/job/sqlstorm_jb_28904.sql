
WITH TitleActorInfo AS (
    SELECT
        at.title AS movie_title,
        ak.name AS actor_name,
        at.production_year,
        ak.id AS actor_id,
        at.id AS title_id
    FROM
        aka_title at
    JOIN
        cast_info ci ON at.id = ci.movie_id
    JOIN
        aka_name ak ON ci.person_id = ak.person_id
),
KeywordInfo AS (
    SELECT
        m.title AS movie_title,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        aka_title m
    JOIN
        movie_keyword mk ON m.id = mk.movie_id
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY
        m.title
),
MovieCompanyInfo AS (
    SELECT
        at.title AS movie_title,
        c.name AS company_name,
        c.country_code
    FROM
        aka_title at
    JOIN
        movie_companies mc ON at.id = mc.movie_id
    JOIN
        company_name c ON mc.company_id = c.id
)
SELECT
    tai.movie_title,
    tai.actor_name,
    tai.production_year,
    ki.keywords,
    coi.company_name,
    coi.country_code
FROM
    TitleActorInfo tai
LEFT JOIN
    KeywordInfo ki ON tai.movie_title = ki.movie_title
LEFT JOIN
    MovieCompanyInfo coi ON tai.movie_title = coi.movie_title
WHERE
    tai.production_year BETWEEN 2000 AND 2020
GROUP BY
    tai.movie_title,
    tai.actor_name,
    tai.production_year,
    ki.keywords,
    coi.company_name,
    coi.country_code;
