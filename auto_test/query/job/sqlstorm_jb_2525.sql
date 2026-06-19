WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
MovieActors AS (
    SELECT 
        c.movie_id,
        a.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rn
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
),
FilteredCompanies AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        COALESCE(NULLIF(mc.note, ''), 'No Note') AS company_note
    FROM 
        movie_companies mc
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    WHERE 
        mc.note IS NOT NULL OR mc.note = '' 
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    STRING_AGG(ma.actor_name, ', ') AS actors,
    fc.company_name,
    fc.company_note
FROM 
    RankedMovies rm
LEFT JOIN 
    MovieActors ma ON rm.movie_id = ma.movie_id
LEFT JOIN 
    FilteredCompanies fc ON rm.movie_id = fc.movie_id
WHERE 
    rm.rn <= 3 AND ma.actor_rn <= 2
GROUP BY 
    rm.movie_id, rm.title, rm.production_year, fc.company_name, fc.company_note;
