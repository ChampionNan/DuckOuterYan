WITH RankedMovies AS (
    SELECT 
        at.id AS movie_id,
        at.title,
        at.production_year,
        DENSE_RANK() OVER (PARTITION BY at.production_year ORDER BY at.id) AS movie_rank,
        COUNT(CASE WHEN ci.role_id IS NOT NULL THEN 1 END) OVER (PARTITION BY at.id) AS cast_count
    FROM 
        aka_title at
    LEFT JOIN 
        cast_info ci ON at.movie_id = ci.movie_id
    WHERE 
        at.production_year IS NOT NULL
),
CharacterCounts AS (
    SELECT 
        a.id AS person_id,
        a.name,
        LENGTH(a.name) - LENGTH(REPLACE(a.name, ' ', '')) + 1 AS word_count,
        LEAD(LENGTH(a.name) - LENGTH(REPLACE(a.name, ' ', '')) + 1) OVER (ORDER BY a.id) AS next_word_count
    FROM 
        aka_name a
    WHERE 
        a.name IS NOT NULL AND a.name <> ''
),
MovieInfoWithKeywords AS (
    SELECT 
        r.movie_id,
        STRING_AGG(DISTINCT k.keyword, ', ') AS keywords
    FROM 
        RankedMovies r
    LEFT JOIN 
        movie_keyword mk ON r.movie_id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        r.movie_id
)
SELECT 
    DISTINCT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.cast_count,
    m.keywords,
    ch.person_id,
    ch.name,
    ch.word_count,
    COALESCE(ch.next_word_count, 0) AS next_word_count
FROM 
    RankedMovies rm
LEFT JOIN 
    MovieInfoWithKeywords m ON rm.movie_id = m.movie_id
LEFT OUTER JOIN 
    CharacterCounts ch ON rm.movie_id = ch.person_id
WHERE 
    rm.cast_count > 0 AND 
    (ch.word_count IS NULL OR ch.word_count = 1 OR ch.word_count <> 2);
