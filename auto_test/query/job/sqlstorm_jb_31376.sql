
WITH RECURSIVE MovieHierarchy AS (
    SELECT m.id AS movie_id, m.title, 0 AS level
    FROM aka_title m
    WHERE m.production_year > 2000
    
    UNION ALL
    
    SELECT m.id AS movie_id, m.title, mh.level + 1
    FROM aka_title m
    JOIN MovieHierarchy mh ON m.episode_of_id = mh.movie_id
),
RoleCount AS (
    SELECT ci.movie_id, COUNT(ci.id) AS role_count
    FROM cast_info ci
    GROUP BY ci.movie_id
),
MoviesWithRoleDetails AS (
    SELECT 
        mh.movie_id,
        mh.title,
        COALESCE(rc.role_count, 0) AS role_count,
        CASE 
            WHEN rc.role_count > 5 THEN 'Large Cast'
            WHEN rc.role_count BETWEEN 3 AND 5 THEN 'Medium Cast'
            ELSE 'Small Cast' 
        END AS cast_size
    FROM MovieHierarchy mh
    LEFT JOIN RoleCount rc ON mh.movie_id = rc.movie_id
),
TopMovies AS (
    SELECT 
        m.movie_id,
        m.title,
        m.role_count,
        m.cast_size,
        ROW_NUMBER() OVER (PARTITION BY m.cast_size ORDER BY m.role_count DESC) AS rn
    FROM MoviesWithRoleDetails m
)

SELECT 
    tm.title,
    m.production_year,
    tm.role_count,
    tm.cast_size,
    nk.keyword AS popular_keyword
FROM TopMovies tm
LEFT JOIN aka_title m ON tm.movie_id = m.id
LEFT JOIN movie_keyword mk ON tm.movie_id = mk.movie_id
LEFT JOIN keyword nk ON mk.keyword_id = nk.id
WHERE tm.rn <= 5;
