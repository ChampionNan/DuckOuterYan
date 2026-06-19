WITH RECURSIVE RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        COALESCE(CAST(ki.keyword AS text), 'No Keywords') AS keyword,
        COALESCE(c.name, 'Unknown Company') AS company_name,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS rn
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword ki ON mk.keyword_id = ki.id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    WHERE 
        t.production_year IS NOT NULL
    AND 
        t.production_year > 2000
),
MovieDetails AS (
    SELECT 
        m.movie_id,
        m.title,
        m.keyword,
        m.company_name,
        DENSE_RANK() OVER (ORDER BY m.production_year DESC) AS year_rank
    FROM 
        RankedMovies m
    WHERE 
        m.rn <= 5
),
FinalOutput AS (
    SELECT 
        md.title,
        md.keyword,
        md.company_name,
        CASE 
            WHEN md.year_rank = 1 THEN 'Latest Movie'
            WHEN md.year_rank > 1 AND md.year_rank <= 5 THEN 'Recent Movie'
            ELSE 'Older Movie'
        END AS movie_age_category,
        EXISTS (
            SELECT 1 
            FROM movie_info mi 
            WHERE mi.movie_id = md.movie_id 
            AND mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Award')
        ) AS has_award_info
    FROM 
        MovieDetails md
)
SELECT 
    f.title,
    f.keyword,
    f.company_name,
    f.movie_age_category,
    CASE 
        WHEN f.has_award_info THEN 'This movie has received awards.'
        ELSE 'This movie has not received any known awards.'
    END AS award_status
FROM 
    FinalOutput f
WHERE 
    f.keyword LIKE '%Drama%';
