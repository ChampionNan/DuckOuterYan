WITH RankedTitles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
),
ActorDetails AS (
    SELECT
        a.id AS actor_id,
        a.name,
        c.movie_id,
        c.role_id,
        r.role,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY c.nr_order) AS actor_rank
    FROM
        aka_name a
    JOIN
        cast_info c ON a.person_id = c.person_id
    JOIN
        role_type r ON c.role_id = r.id
),
MovieCompanies AS (
    SELECT
        m.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY m.movie_id ORDER BY c.name) AS company_rank
    FROM
        movie_companies m
    JOIN
        company_name c ON m.company_id = c.id
    JOIN
        company_type ct ON m.company_type_id = ct.id
),
KeywordAssociations AS (
    SELECT
        mk.movie_id,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY mk.movie_id ORDER BY k.keyword) AS keyword_rank
    FROM
        movie_keyword mk
    JOIN
        keyword k ON mk.keyword_id = k.id
)
SELECT
    rt.title,
    rt.production_year,
    ad.name AS actor_name,
    ad.role,
    mc.company_name,
    mc.company_type,
    ka.keyword
FROM
    RankedTitles rt
LEFT JOIN
    ActorDetails ad ON rt.title_id = ad.movie_id AND ad.actor_rank <= 3
LEFT JOIN
    MovieCompanies mc ON rt.title_id = mc.movie_id AND mc.company_rank <= 2
LEFT JOIN
    KeywordAssociations ka ON rt.title_id = ka.movie_id AND ka.keyword_rank <= 5
WHERE
    rt.rank <= 10;
