WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank,
        COUNT(*) OVER (PARTITION BY t.production_year) AS total_titles
    FROM 
        aka_title t
    WHERE 
        t.kind_id IN (SELECT id FROM kind_type WHERE kind = 'movie') 
        AND t.production_year IS NOT NULL
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        an.name AS actor_name,
        r.role AS role_name,
        COALESCE(NULLIF(ci.note, ''), 'No Note') AS actor_note
    FROM 
        cast_info ci
    JOIN 
        aka_name an ON ci.person_id = an.person_id
    LEFT JOIN 
        role_type r ON ci.role_id = r.id
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        mk.movie_id
)
SELECT 
    rm.title,
    rm.production_year,
    cd.actor_name,
    cd.role_name,
    cd.actor_note,
    mk.keywords,
    rm.title_rank,
    rm.total_titles,
    CASE 
        WHEN rm.title_rank = 1 THEN 'First Title of Year'
        ELSE 'Not First Title'
    END AS title_status,
    CASE 
        WHEN mk.keywords IS NULL THEN 'No Keywords'
        ELSE mk.keywords
    END AS adjusted_keywords
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE 
    (cd.role_name IS NOT NULL OR cd.actor_note != 'No Note')
    AND rm.production_year >= 2000;
