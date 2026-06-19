WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        a.kind_id,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC) AS year_rank
    FROM 
        aka_title a
    JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        k.keyword ILIKE '%drama%'
),
CastDetails AS (
    SELECT 
        ci.person_id, 
        ci.movie_id, 
        p.name,
        rt.role AS role_description,
        COUNT(*) OVER (PARTITION BY ci.movie_id) AS cast_count
    FROM 
        cast_info ci
    JOIN 
        name p ON ci.person_id = p.id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        p.gender = 'F' 
        AND p.name ILIKE '%.%'
),
MovieInfoExtended AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        cd.cast_count,
        STRING_AGG(cd.name, ', ') AS female_cast,
        rt.kind AS movie_genre
    FROM 
        RankedMovies rm
    LEFT JOIN 
        CastDetails cd ON rm.movie_id = cd.movie_id
    LEFT JOIN 
        kind_type rt ON rm.kind_id = rt.id
    WHERE 
        rm.year_rank <= 10
    GROUP BY 
        rm.movie_id, rm.title, rm.production_year, cd.cast_count, rt.kind
)

SELECT 
    mie.title,
    mie.production_year,
    mie.cast_count,
    mie.female_cast,
    mie.movie_genre
FROM 
    MovieInfoExtended mie;
