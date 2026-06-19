WITH RankedTitles AS (
    SELECT 
        at.title AS movie_title,
        at.production_year,
        ak.name AS actor_name,
        ROW_NUMBER() OVER (PARTITION BY at.id ORDER BY ak.name) AS actor_rank
    FROM 
        aka_title at
    JOIN 
        cast_info ci ON at.id = ci.movie_id
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    WHERE 
        at.production_year BETWEEN 2000 AND 2020
),
KeywordCounts AS (
    SELECT 
        movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM 
        movie_keyword mk
    GROUP BY 
        movie_id
),
MovieGenre AS (
    SELECT 
        title.id AS movie_id,
        kt.kind AS genre
    FROM 
        title
    JOIN 
        kind_type kt ON title.kind_id = kt.id
)
SELECT 
    rt.movie_title,
    rt.production_year,
    rt.actor_name,
    kc.keyword_count,
    mg.genre
FROM 
    RankedTitles rt
LEFT JOIN 
    KeywordCounts kc ON rt.movie_title = (SELECT title FROM aka_title WHERE id = kc.movie_id LIMIT 1)
LEFT JOIN 
    MovieGenre mg ON rt.production_year = mg.movie_id
WHERE 
    rt.actor_rank = 1;
