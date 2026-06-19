WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        0 AS level
    FROM 
        aka_title m
    WHERE 
        m.production_year >= 2000 
    UNION ALL
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        mh.level + 1
    FROM 
        aka_title m
    JOIN MovieHierarchy mh ON m.episode_of_id = mh.movie_id
), 

RankedActors AS (
    SELECT 
        c.movie_id,
        a.name,
        RANK() OVER (PARTITION BY c.movie_id ORDER BY a.name) AS actor_rank
    FROM 
        cast_info c
    JOIN aka_name a ON c.person_id = a.person_id
    WHERE 
        a.name IS NOT NULL
), 

MovieKeywordCounts AS (
    SELECT 
        mk.movie_id,
        COUNT(mk.keyword_id) AS keyword_count
    FROM 
        movie_keyword mk
    GROUP BY 
        mk.movie_id
), 

FilteredMovies AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        COALESCE(mkc.keyword_count, 0) AS keyword_count,
        ra.actor_rank
    FROM 
        MovieHierarchy mh
    LEFT JOIN MovieKeywordCounts mkc ON mh.movie_id = mkc.movie_id
    LEFT JOIN RankedActors ra ON mh.movie_id = ra.movie_id
    WHERE 
        mh.level < 2
), 

TopMovies AS (
    SELECT 
        f.*,
        ROW_NUMBER() OVER (ORDER BY f.production_year DESC, f.keyword_count DESC) AS rn
    FROM 
        FilteredMovies f
)
SELECT 
    tm.title,
    tm.production_year,
    tm.keyword_count,
    tm.actor_rank
FROM 
    TopMovies tm
WHERE 
    tm.rn <= 10;
