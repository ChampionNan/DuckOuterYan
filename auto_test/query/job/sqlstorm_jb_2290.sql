WITH MovieDetails AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS keyword_rank
    FROM 
        aka_title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        t.production_year IS NOT NULL
),
ActorInfo AS (
    SELECT 
        a.name AS actor_name,
        c.movie_id,
        COUNT(*) AS appearance_count
    FROM 
        cast_info c
    JOIN 
        aka_name a ON c.person_id = a.person_id
    GROUP BY 
        a.name, c.movie_id
),
FilteredActors AS (
    SELECT
        actor_name,
        movie_id,
        appearance_count,
        ROW_NUMBER() OVER (PARTITION BY appearance_count ORDER BY actor_name) AS appearance_rank
    FROM 
        ActorInfo
    WHERE 
        appearance_count > 1
)
SELECT 
    md.movie_id,
    md.title,
    md.production_year,
    fa.actor_name,
    fa.appearance_count,
    fa.appearance_rank,
    COALESCE(md.keyword, 'No Keywords') AS keyword_info
FROM 
    MovieDetails md
JOIN 
    FilteredActors fa ON md.movie_id = fa.movie_id
WHERE 
    (md.production_year > 2000 AND fa.appearance_rank <= 5) OR 
    (md.production_year <= 2000 AND fa.appearance_rank = 1);
