WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_by_year
    FROM 
        aka_title t
    WHERE 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind IN ('movie', 'feature'))
),
CastDetails AS (
    SELECT 
        m.movie_id,
        a.name AS actor_name,
        c.nr_order,
        RANK() OVER (PARTITION BY m.movie_id ORDER BY c.nr_order) AS actor_rank,
        CASE 
            WHEN c.note IS NOT NULL THEN c.note 
            ELSE 'No Note' 
        END AS role_note
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    JOIN 
        RankedMovies m ON c.movie_id = m.movie_id
),
CompanyEntities AS (
    SELECT 
        m.movie_id,
        co.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY m.movie_id ORDER BY co.name) AS company_rank
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON mc.company_id = co.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    JOIN 
        RankedMovies m ON mc.movie_id = m.movie_id
)
SELECT 
    rm.movie_title,
    rm.production_year,
    cd.actor_name,
    cd.actor_rank,
    cd.role_note,
    ce.company_name,
    ce.company_type,
    ce.company_rank
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id AND cd.actor_rank <= 5 
LEFT JOIN 
    CompanyEntities ce ON rm.movie_id = ce.movie_id
WHERE 
    rm.rank_by_year <= 10;
