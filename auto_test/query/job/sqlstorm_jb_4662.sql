WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
CastDetails AS (
    SELECT 
        ci.movie_id,
        cn.name AS character_name,
        ak.name AS actor_name,
        r.role AS role_type
    FROM 
        cast_info ci
    JOIN 
        char_name cn ON ci.person_id = cn.imdb_id
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN 
        role_type r ON ci.role_id = r.id
),
MovieCompaniesCTE AS (
    SELECT 
        mc.movie_id,
        cm.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cm ON mc.company_id = cm.imdb_id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
MovieInfoCTE AS (
    SELECT 
        mi.movie_id,
        STRING_AGG(DISTINCT mi.info, ', ') AS info_details
    FROM 
        movie_info mi
    GROUP BY 
        mi.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    cd.character_name,
    cd.actor_name,
    cd.role_type,
    mc.company_name,
    mc.company_type,
    mi.info_details
FROM 
    RankedMovies rm
LEFT JOIN 
    CastDetails cd ON rm.movie_id = cd.movie_id
LEFT JOIN 
    MovieCompaniesCTE mc ON rm.movie_id = mc.movie_id
LEFT JOIN 
    MovieInfoCTE mi ON rm.movie_id = mi.movie_id
WHERE 
    rm.rank <= 5
    AND (cd.role_type IS NOT NULL OR mc.company_name IS NOT NULL);
