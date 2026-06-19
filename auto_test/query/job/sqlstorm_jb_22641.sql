WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year, t.title) AS title_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorMovieCTE AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS actor_count,
        CASE
            WHEN ci.nr_order IS NULL THEN 'Unknown role order'
            ELSE CAST(ci.nr_order AS text)
        END AS role_order
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        ak.name IS NOT NULL AND 
        ak.md5sum IS NOT NULL
),
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type,
        COALESCE(mc.note, 'No notes available') AS note
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
)
SELECT 
    m.movie_id,
    m.title,
    m.production_year,
    a.actor_name,
    a.actor_count,
    a.role_order,
    cm.company_name,
    cm.company_type,
    cm.note
FROM 
    RankedMovies m
LEFT JOIN 
    ActorMovieCTE a ON m.movie_id = a.movie_id
LEFT JOIN 
    CompanyMovies cm ON m.movie_id = cm.movie_id
WHERE 
    m.title_rank <= 5 AND
    (a.actor_count > 2 OR cm.company_type IS NOT NULL);
