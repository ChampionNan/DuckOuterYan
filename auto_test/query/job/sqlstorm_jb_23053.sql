WITH RankedMovies AS (
    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.title) AS title_rank,
        COUNT(c.id) OVER (PARTITION BY a.id) AS actor_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_info mi ON a.id = mi.movie_id
    LEFT JOIN 
        complete_cast cc ON a.id = cc.movie_id
    LEFT JOIN 
        cast_info c ON cc.subject_id = c.id
    WHERE 
        a.production_year IS NOT NULL
        AND a.title IS NOT NULL
        AND EXISTS (
            SELECT 1 
            FROM movie_keyword mk 
            WHERE mk.movie_id = a.id
            AND mk.keyword_id IN (
                SELECT id FROM keyword WHERE keyword LIKE '%action%'
            )
        )
),
DetailedActors AS (
    SELECT 
        ak.person_id,
        ak.name,
        COUNT(*) OVER (PARTITION BY ak.person_id) AS movie_count,
        MAX(CASE WHEN ci.nr_order = 1 THEN ak.name END) OVER (PARTITION BY ak.person_id) AS main_role
    FROM 
        aka_name ak
    LEFT JOIN 
        cast_info ci ON ak.person_id = ci.person_id
),
UniqueTitles AS (
    SELECT DISTINCT 
        title,
        production_year
    FROM 
        RankedMovies
    WHERE 
        title_rank <= 5
)
SELECT 
    dt.name AS actor_name,
    ut.title AS movie_title,
    ut.production_year,
    dt.movie_count AS films_participated,
    ut.movie_id AS movie_identifier,
    COALESCE(dt.main_role, 'Unknown Role') AS leading_role,
    (SELECT COUNT(DISTINCT ci.id)
     FROM cast_info ci
     WHERE ci.movie_id IN (SELECT movie_id FROM RankedMovies)) AS cast_count_in_action_movies
FROM 
    DetailedActors dt
JOIN 
    RankedMovies ut ON dt.person_id = ut.movie_id
WHERE 
    dt.movie_count >= 1 
    AND ut.actor_count > 0;
