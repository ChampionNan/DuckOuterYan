WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS rank_year,
        COUNT(DISTINCT mk.keyword_id) AS keyword_count
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    WHERE 
        t.production_year IS NOT NULL
    GROUP BY 
        t.id, t.title, t.production_year
),
MovieDetails AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(cast_info.nr_order, 0) AS nr_order,
        COALESCE(cn.name, 'Unknown') AS company_name,
        CASE 
            WHEN rm.keyword_count > 5 THEN 'Many Keywords'
            ELSE 'Few Keywords'
        END AS keyword_category
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_companies mc ON rm.movie_id = mc.movie_id
    LEFT JOIN 
        company_name cn ON mc.company_id = cn.id
    LEFT JOIN 
        complete_cast cc ON rm.movie_id = cc.movie_id
    LEFT JOIN 
        cast_info cast_info ON cc.subject_id = cast_info.person_id
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    md.nr_order,
    md.company_name,
    md.keyword_category
FROM 
    MovieDetails md
WHERE 
    (md.nr_order IS NULL OR md.nr_order > 0)
    AND md.keyword_category = 'Many Keywords'
    AND md.production_year BETWEEN 2000 AND 2020;
