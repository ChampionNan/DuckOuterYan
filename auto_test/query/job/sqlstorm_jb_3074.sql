
WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY c.nr_order) AS rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        cast_info c ON t.id = c.movie_id
    WHERE 
        cn.country_code IS NOT NULL
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
),
TopMovies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        mk.keywords
    FROM 
        RankedMovies rm
    LEFT JOIN 
        MovieKeywords mk ON rm.movie_id = mk.movie_id
    WHERE 
        rm.rank <= 5
)

SELECT 
    tm.title,
    COALESCE(CAST(tm.production_year AS VARCHAR), 'Unknown') AS production_year,
    COALESCE(tm.keywords, 'No Keywords') AS keywords
FROM 
    TopMovies tm
WHERE 
    EXISTS (
        SELECT 
            1 
        FROM 
            complete_cast cc 
        WHERE 
            cc.movie_id = tm.movie_id
            AND cc.status_id IS NOT NULL
    );
