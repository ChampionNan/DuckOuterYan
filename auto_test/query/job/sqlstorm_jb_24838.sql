WITH RankedTitles AS (
    SELECT
        t.id AS title_id,
        t.title,
        t.production_year,
        t.kind_id,
        RANK() OVER (PARTITION BY t.kind_id ORDER BY t.production_year DESC) AS year_rank
    FROM
        aka_title t
    WHERE
        t.production_year IS NOT NULL
        AND t.title IS NOT NULL
),
ActorRoles AS (
    SELECT
        ci.movie_id,
        a.name AS actor_name,
        r.role AS actor_role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM
        cast_info ci
        JOIN aka_name a ON ci.person_id = a.person_id
        JOIN role_type r ON ci.role_id = r.id
),
MovieKeywords AS (
    SELECT
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        movie_keyword mk
        JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY
        mk.movie_id
),
CompanyInfo AS (
    SELECT
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM
        movie_companies mc
        JOIN company_name c ON mc.company_id = c.id
        JOIN company_type ct ON mc.company_type_id = ct.id
),
FinalSelection AS (
    SELECT
        t.title,
        t.production_year,
        a.actor_name,
        a.actor_role,
        COALESCE(mk.keywords, 'No keywords') AS keywords,
        c.company_name,
        c.company_type
    FROM 
        RankedTitles t
        LEFT JOIN ActorRoles a ON t.title_id = a.movie_id
        LEFT JOIN MovieKeywords mk ON t.title_id = mk.movie_id
        LEFT JOIN CompanyInfo c ON t.title_id = c.movie_id
    WHERE
        t.year_rank = 1
        AND (a.actor_name IS NOT NULL OR c.company_name IS NOT NULL)
)
SELECT
    title,
    production_year,
    actor_name,
    actor_role,
    keywords,
    company_name,
    company_type
FROM
    FinalSelection
WHERE
    (actor_role LIKE '%Lead%' OR company_type IS NULL);
