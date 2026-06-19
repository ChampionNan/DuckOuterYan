
WITH RecursiveCTE AS (
    SELECT 
        m.id AS movie_id, 
        m.title AS movie_title, 
        COALESCE(k.keyword, 'No Keywords') AS keyword,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        aka_title m
    LEFT JOIN 
        movie_keyword mk ON m.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        m.production_year >= 2000
),
AggregateRoles AS (
    SELECT 
        ci.movie_id, 
        STRING_AGG(r.role, ', ') AS roles_combined
    FROM 
        cast_info ci
    JOIN 
        role_type r ON ci.role_id = r.id
    GROUP BY 
        ci.movie_id
),
RankedMovies AS (
    SELECT 
        m.movie_id,
        m.movie_title,
        a.roles_combined,
        m.keyword,
        RANK() OVER (ORDER BY m.movie_title ASC) AS movie_rank
    FROM 
        RecursiveCTE m
    LEFT JOIN 
        AggregateRoles a ON m.movie_id = a.movie_id
)
SELECT 
    rm.movie_id,
    rm.movie_title,
    rm.roles_combined,
    rm.keyword,
    CASE 
        WHEN rm.keyword IS NULL THEN 'No Data'
        ELSE 'Keyword Found'
    END AS keyword_status,
    SUM(CASE 
        WHEN rm.roles_combined LIKE '%Director%' THEN 1 
        ELSE 0 
    END) OVER () AS total_directors
FROM 
    RankedMovies rm
WHERE 
    rm.movie_rank <= 100
GROUP BY 
    rm.movie_id, 
    rm.movie_title, 
    rm.roles_combined, 
    rm.keyword;
