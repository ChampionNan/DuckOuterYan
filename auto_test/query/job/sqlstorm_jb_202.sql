WITH MovieDetails AS (
    SELECT 
        t.title,
        t.production_year,
        k.keyword,
        CTEA.actor_count,
        RANK() OVER (PARTITION BY t.production_year ORDER BY CTEA.actor_count DESC) AS rank_count
    FROM
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN (
        SELECT 
            ci.movie_id,
            COUNT(DISTINCT ci.person_id) AS actor_count
        FROM 
            cast_info ci
        GROUP BY 
            ci.movie_id
    ) CTEA ON t.id = CTEA.movie_id
    WHERE 
        t.production_year IS NOT NULL
)

SELECT 
    md.title,
    md.production_year,
    COALESCE(md.keyword, 'No Keyword') AS keyword,
    md.actor_count,
    CASE 
        WHEN md.actor_count IS NULL THEN 'Unknown'
        WHEN md.actor_count > 10 THEN 'Popular'
        ELSE 'Less Popular'
    END AS popularity
FROM 
    MovieDetails md
WHERE 
    md.rank_count <= 5;
