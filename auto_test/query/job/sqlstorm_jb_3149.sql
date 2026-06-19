WITH RankedMovies AS (
    SELECT 
        a.id AS actor_id,
        a.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.id ORDER BY t.production_year DESC) AS rn
    FROM
        aka_name a
    JOIN cast_info c ON a.person_id = c.person_id
    JOIN aka_title t ON c.movie_id = t.movie_id
    WHERE 
        t.production_year IS NOT NULL
        AND a.name IS NOT NULL
),
FilteredMovies AS (
    SELECT 
        actor_id,
        actor_name,
        movie_title,
        production_year
    FROM 
        RankedMovies
    WHERE 
        rn <= 5
),
MovieKeywords AS (
    SELECT 
        m.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword m
    JOIN keyword k ON m.keyword_id = k.id
    GROUP BY 
        m.movie_id
),
DistinctMovieCompanies AS (
    SELECT DISTINCT 
        mc.movie_id,
        cn.name AS company_name
    FROM 
        movie_companies mc
    JOIN company_name cn ON mc.company_id = cn.id
)

SELECT 
    fm.actor_name,
    fm.movie_title,
    fm.production_year,
    COALESCE(mk.keywords, 'No Keywords') AS keywords,
    COALESCE(cm.company_name, 'Unknown Company') AS company_name
FROM 
    FilteredMovies fm
LEFT JOIN 
    MovieKeywords mk ON fm.production_year = mk.movie_id
LEFT JOIN 
    DistinctMovieCompanies cm ON fm.production_year = cm.movie_id
WHERE 
    fm.production_year >= 2000;
