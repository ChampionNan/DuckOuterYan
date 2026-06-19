WITH MovieInfo AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        a.name AS main_actor,
        c.kind AS company_type,
        m.info AS review
    FROM 
        aka_title t
    JOIN 
        cast_info ci ON t.id = ci.movie_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_type c ON mc.company_type_id = c.id
    LEFT JOIN 
        movie_info m ON t.id = m.movie_id AND m.info_type_id = (
            SELECT id FROM info_type WHERE info = 'Review' LIMIT 1
        )
    WHERE 
        a.name IS NOT NULL AND
        c.kind IS NOT NULL
),
KeywordFiltered AS (
    SELECT 
        movie_id,
        STRING_AGG(keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        movie_id
),
FinalOutput AS (
    SELECT 
        mi.movie_id,
        mi.title,
        mi.production_year,
        mi.main_actor,
        mi.company_type,
        kf.keywords,
        COALESCE(mi.review, 'No Review Available') AS review
    FROM 
        MovieInfo mi
    LEFT JOIN 
        KeywordFiltered kf ON mi.movie_id = kf.movie_id
)
SELECT 
    *,
    CONCAT('Movie: ', title, ' was released in ', production_year, '. Starring: ', main_actor, '. Produced by: ', company_type, '. Keywords: ', COALESCE(keywords, 'N/A'), '. Review: ', review) AS movie_description
FROM 
    FinalOutput;
