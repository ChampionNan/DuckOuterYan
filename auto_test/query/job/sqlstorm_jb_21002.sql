WITH MovieRoleCounts AS (
    SELECT 
        c.movie_id,
        r.role AS role_type,
        COUNT(c.id) AS role_count
    FROM 
        cast_info c
    JOIN 
        role_type r ON c.role_id = r.id
    GROUP BY 
        c.movie_id, r.role
),
TopRoles AS (
    SELECT 
        movie_id, 
        role_type,
        role_count,
        RANK() OVER (PARTITION BY movie_id ORDER BY role_count DESC) AS rank
    FROM 
        MovieRoleCounts
),
MoviesWithInfo AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        COALESCE(mi.info, 'No Info') AS info,
        k.keyword AS keyword
    FROM 
        aka_title t
    LEFT JOIN 
        movie_info mi ON t.id = mi.movie_id
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
)
SELECT 
    m.movie_id,
    m.title,
    m.production_year,
    CASE 
        WHEN tr.role_count IS NULL THEN 'No Roles Found'
        ELSE CONCAT('Top Role: ', tr.role_type, ' (Count: ', tr.role_count, ')')
    END AS top_role_info,
    m.info,
    m.keyword
FROM 
    MoviesWithInfo m
LEFT JOIN 
    TopRoles tr ON m.movie_id = tr.movie_id AND tr.rank = 1
WHERE 
    m.production_year IS NOT NULL
    AND (m.info LIKE '%Epic%' OR m.info IS NULL);
