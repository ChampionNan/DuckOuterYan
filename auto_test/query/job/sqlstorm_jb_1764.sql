WITH RankedTitles AS (
    SELECT 
        a.person_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS rnk
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.movie_id
    WHERE 
        a.name IS NOT NULL
    AND 
        t.production_year IS NOT NULL
),
DistinctKeywords AS (
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
CompleteInfo AS (
    SELECT 
        m.title AS movie_title,
        COALESCE(k.keywords, 'No Keywords') AS keywords,
        CASE 
            WHEN r.rnk = 1 THEN 'Latest'
            ELSE 'Older'
        END AS title_status
    FROM 
        title m
    LEFT JOIN 
        RankedTitles r ON m.imdb_id = r.person_id
    LEFT JOIN 
        DistinctKeywords k ON m.id = k.movie_id
)
SELECT 
    movie_title,
    keywords,
    title_status
FROM 
    CompleteInfo
WHERE 
    title_status = 'Latest';
