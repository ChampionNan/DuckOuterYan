WITH RankedMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        RANK() OVER (PARTITION BY t.production_year ORDER BY t.id) AS year_rank
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorCounts AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
CommentedMovies AS (
    SELECT 
        m.movie_id,
        m.title,
        COALESCE(m.note, 'No comments') AS movie_comment
    FROM 
        aka_title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
    WHERE 
        mi.info_type_id = (SELECT id FROM info_type WHERE info = 'Comment')
),
TopMovies AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        ac.actor_count,
        cm.movie_comment
    FROM 
        RankedMovies rm
    LEFT JOIN 
        ActorCounts ac ON rm.movie_id = ac.movie_id
    LEFT JOIN 
        CommentedMovies cm ON rm.movie_id = cm.movie_id
    WHERE 
        rm.year_rank <= 3  
)
SELECT 
    tm.title,
    tm.production_year,
    tm.actor_count,
    CASE 
        WHEN tm.movie_comment IS NOT NULL THEN tm.movie_comment 
        ELSE 'No comments available' 
    END AS comment_status,
    CASE 
        WHEN tm.actor_count IS NULL THEN 'No actors listed' 
        ELSE CONCAT('This movie has ', tm.actor_count, ' actor(s).') 
    END AS actor_status
FROM 
    TopMovies tm
WHERE 
    tm.production_year >= 2000;
